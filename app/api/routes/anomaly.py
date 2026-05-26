"""
GET /anomalies         — paginated list of anomalous log entries
GET /anomalies/summary — aggregate statistics (TTL-cached for 30 s)
"""

from __future__ import annotations

import time
from collections import Counter
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Query, status

from app.core.logger import get_logger
from app.core.rate_limit import read_limiter
from app.models.query_models import (
    AnomalyEntry,
    AnomalyListResponse,
    AnomalySummaryResponse,
)
from app.services import vector_store as vs
from app.services.vector_store import count_anomalies

logger = get_logger(__name__)
router = APIRouter(prefix="/anomalies", tags=["anomalies"])

# ---------------------------------------------------------------------------
# Summary TTL cache — avoids fetching up to 10 000 documents on every poll
# ---------------------------------------------------------------------------

_SUMMARY_CACHE_TTL: float = 30.0   # seconds
_summary_cache: Optional[AnomalySummaryResponse] = None
_summary_cache_at: float = 0.0


def _invalidate_summary_cache() -> None:
    """Call after ingest operations to force a fresh summary on next request."""
    global _summary_cache_at
    _summary_cache_at = 0.0


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get(
    "",
    response_model=AnomalyListResponse,
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(read_limiter)],
)
async def list_anomalies(
    limit: int = Query(50, ge=1, le=200, description="Max results to return"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    min_score: float = Query(0.0, ge=-1.0, le=1.0, description="Minimum |anomaly_score| to include"),
) -> AnomalyListResponse:
    """
    Return a paginated list of log entries flagged as anomalies.
    """
    raw = vs.get_all_anomalies(limit=limit, offset=offset, min_score=min_score)

    items: List[AnomalyEntry] = []
    for doc_id, doc, meta in zip(raw["ids"], raw["documents"], raw["metadatas"]):
        items.append(
            AnomalyEntry(
                id=doc_id,
                document=doc,
                is_anomaly=bool(meta.get("is_anomaly", True)),
                anomaly_score=float(meta.get("anomaly_score", 0.0)),
                metadata=meta,
            )
        )

    # Efficient total count — no document fetch needed
    total = count_anomalies(min_score=min_score)

    return AnomalyListResponse(
        items=items,
        total=total,
        offset=offset,
        limit=limit,
    )


@router.get(
    "/summary",
    response_model=AnomalySummaryResponse,
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(read_limiter)],
)
async def anomaly_summary() -> AnomalySummaryResponse:
    """
    Return aggregate statistics about all ingested logs.

    The result is cached for 30 s to avoid expensive full-collection scans
    on every frontend poll cycle.
    """
    global _summary_cache, _summary_cache_at

    # Serve from cache if fresh
    if _summary_cache is not None and (time.monotonic() - _summary_cache_at) < _SUMMARY_CACHE_TTL:
        return _summary_cache

    # ── Total logs ───────────────────────────────────────────────────────────
    stats = vs.get_collection_stats()
    total_logs = stats["count"]

    # ── Anomaly count and metadata ───────────────────────────────────────────
    # Fetch only IDs + metadata (no document text) to keep this fast.
    # Limit is set conservatively; for very large collections, this
    # could be replaced with a streaming/batch approach.
    _MAX_SUMMARY_DOCS = 5_000
    anomaly_raw = vs.get_all_anomalies(limit=_MAX_SUMMARY_DOCS, offset=0)
    total_anomalies = len(anomaly_raw["ids"])

    # Anomaly rate as a fraction (0.0–1.0) — NOT a percentage.
    # The frontend Hero component multiplies by 100 for display.
    anomaly_rate = (total_anomalies / total_logs) if total_logs > 0 else 0.0

    # ── Status-code breakdown and top IPs ────────────────────────────────────
    status_counter: Counter = Counter()
    ip_counter: Counter = Counter()

    for meta in anomaly_raw["metadatas"]:
        sc = str(meta.get("status_code", "unknown"))
        if sc and sc != "0":
            status_counter[sc] += 1
        ip = meta.get("source_ip", "")
        if ip:
            ip_counter[ip] += 1

    top_ips: List[Dict[str, Any]] = [
        {"ip": ip, "count": count}
        for ip, count in ip_counter.most_common(10)
    ]

    result = AnomalySummaryResponse(
        total_logs=total_logs,
        total_anomalies=total_anomalies,
        anomaly_rate=round(anomaly_rate, 4),
        status_code_breakdown=dict(status_counter.most_common(20)),
        top_suspicious_ips=top_ips,
    )

    # Store in cache
    _summary_cache = result
    _summary_cache_at = time.monotonic()

    return result
