"""
GET /anomalies         — paginated list of anomalous log entries
GET /anomalies/summary — aggregate statistics
"""

from __future__ import annotations

from collections import Counter
from typing import Any, Dict, List

from fastapi import APIRouter, Query, status

from app.core.logger import get_logger
from app.models.query_models import (
    AnomalyEntry,
    AnomalyListResponse,
    AnomalySummaryResponse,
)
from app.services import vector_store as vs

logger = get_logger(__name__)
router = APIRouter(prefix="/anomalies", tags=["anomalies"])


@router.get("", response_model=AnomalyListResponse, status_code=status.HTTP_200_OK)
async def list_anomalies(
    limit: int = Query(50, ge=1, le=200, description="Max results to return"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    min_score: float = Query(0.0, ge=-1.0, le=1.0, description="Minimum absolute anomaly score"),
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

    # Total count query (without pagination)
    total_raw = vs.get_all_anomalies(limit=10_000, offset=0, min_score=min_score)
    total = len(total_raw["ids"])

    return AnomalyListResponse(
        items=items,
        total=total,
        offset=offset,
        limit=limit,
    )


@router.get("/summary", response_model=AnomalySummaryResponse, status_code=status.HTTP_200_OK)
async def anomaly_summary() -> AnomalySummaryResponse:
    """
    Return aggregate statistics about all ingested logs.
    """
    # Total logs
    stats = vs.get_collection_stats()
    total_logs = stats["count"]

    # All anomalous docs
    anomaly_raw = vs.get_all_anomalies(limit=10_000, offset=0)
    total_anomalies = len(anomaly_raw["ids"])
    anomaly_rate = (total_anomalies / total_logs * 100) if total_logs > 0 else 0.0

    # Compute status_code breakdown and top IPs from anomaly metadata
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

    return AnomalySummaryResponse(
        total_logs=total_logs,
        total_anomalies=total_anomalies,
        anomaly_rate=round(anomaly_rate, 2),
        status_code_breakdown=dict(status_counter.most_common(20)),
        top_suspicious_ips=top_ips,
    )
