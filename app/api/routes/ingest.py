"""
POST /ingest       — multipart file upload
POST /ingest/text  — raw log text in request body
"""

from __future__ import annotations

import io
import time
import uuid
from typing import List

from fastapi import APIRouter, File, HTTPException, Request, UploadFile, status

from app.core.logger import get_logger
from app.models.log_entry import LogEntry
from app.models.query_models import IngestResponse, IngestTextRequest
from app.services import vector_store as vs
from app.services.anomaly_detector import get_detector
from app.services.ingestion import chunk_logs, load_log_file
from app.utils.log_parser import auto_detect_and_parse

logger = get_logger(__name__)
router = APIRouter(prefix="/ingest", tags=["ingestion"])

MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _process_entries(entries: List[LogEntry]) -> IngestResponse:
    """Run anomaly detection, chunk, embed, and store; return response."""
    t_start = time.perf_counter()

    settings_obj = vs.get_collection_stats  # just to import config lazily
    from app.core.config import get_settings  # noqa: PLC0415
    settings = get_settings()

    # ── Anomaly detection ────────────────────────────────────────────────────
    detector = get_detector()
    if not detector.is_fitted and entries:
        detector.fit(entries)

    anomaly_results = []
    anomalies_found = 0
    if detector.is_fitted:
        anomaly_results = detector.predict(entries)
        anomalies_found = sum(1 for r in anomaly_results if r.is_anomaly)
        # Annotate entries with anomaly info
        for entry, result in zip(entries, anomaly_results):
            entry.is_anomaly = result.is_anomaly
            entry.anomaly_score = result.anomaly_score

    # ── Chunk ────────────────────────────────────────────────────────────────
    chunks = chunk_logs(
        entries,
        chunk_size=settings.max_chunk_size,
        overlap=settings.chunk_overlap,
    )

    # ── Build metadata ───────────────────────────────────────────────────────
    metadatas = []
    ids = []
    for i, chunk in enumerate(chunks):
        doc_id = str(uuid.uuid4())
        ids.append(doc_id)
        # Attach anomaly metadata from the first entry that contributed to this chunk
        # (simplification: use chunk index to approximate)
        entry_idx = min(i, len(entries) - 1)
        entry = entries[entry_idx]
        metadatas.append({
            "chunk_index":  i,
            "is_anomaly":   entry.is_anomaly,
            "anomaly_score": entry.anomaly_score,
            "source_ip":    entry.source_ip or "",
            "status_code":  entry.status_code or 0,
            "path":         entry.path or entry.message[:50] if entry.message else "",
        })

    # ── Store ─────────────────────────────────────────────────────────────────
    if chunks:
        vs.add_documents(chunks=chunks, metadatas=metadatas, ids=ids)

    elapsed_ms = int((time.perf_counter() - t_start) * 1000)
    return IngestResponse(
        ingested_lines=len(entries),
        chunks_stored=len(chunks),
        anomalies_found=anomalies_found,
        time_ms=elapsed_ms,
    )


def _parse_raw_text(text: str) -> List[LogEntry]:
    """Parse raw multi-line log text into LogEntry objects."""
    entries: List[LogEntry] = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            parsed = auto_detect_and_parse(line)
            if parsed:
                entries.append(LogEntry.from_parsed_dict(parsed))
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"Line {lineno}: parse error ({exc}), skipping")
    return entries


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.post("", response_model=IngestResponse, status_code=status.HTTP_200_OK)
async def ingest_file(file: UploadFile = File(...)) -> IngestResponse:
    """
    Upload a .log or .txt file to ingest into the vector database.

    Max file size: 10 MB.
    """
    # Validate content type / extension
    filename = file.filename or ""
    if not filename.lower().endswith((".log", ".txt")):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Only .log and .txt files are accepted.",
        )

    content = await file.read()
    if len(content) > MAX_FILE_SIZE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds 10 MB limit ({len(content) / 1024 / 1024:.1f} MB).",
        )

    try:
        text = content.decode("utf-8", errors="replace")
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Could not decode file as UTF-8: {exc}",
        ) from exc

    entries = _parse_raw_text(text)
    if not entries:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="No parseable log lines found in the uploaded file.",
        )

    logger.info(f"Ingesting file '{filename}': {len(entries)} entries")
    return _process_entries(entries)


@router.post("/text", response_model=IngestResponse, status_code=status.HTTP_200_OK)
async def ingest_text(body: IngestTextRequest) -> IngestResponse:
    """
    Ingest raw log text sent in the request body.
    Useful for testing without file upload.
    """
    entries = _parse_raw_text(body.text)
    if not entries:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="No parseable log lines found in the provided text.",
        )
    logger.info(f"Ingesting text: {len(entries)} entries")
    return _process_entries(entries)
