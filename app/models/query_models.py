"""
Request / Response Pydantic schemas for the REST API.

All user-supplied string fields carry explicit max-length constraints to
prevent excessively large payloads from reaching the processing layer.
"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator


# ---------------------------------------------------------------------------
# /ingest
# ---------------------------------------------------------------------------

class IngestResponse(BaseModel):
    """Response from POST /ingest or POST /ingest/text."""
    ingested_lines: int
    chunks_stored: int
    anomalies_found: int
    time_ms: int
    source_name: str | None = None
    upload_id: str | None = None


class IngestTextRequest(BaseModel):
    """Body for POST /ingest/text."""

    text: str = Field(
        ...,
        min_length=1,
        max_length=524_288,   # 512 KB — keeps single requests manageable
        description="Raw log text to ingest (max 512 KB)",
    )

    @field_validator("text")
    @classmethod
    def strip_null_bytes(cls, v: str) -> str:
        """Remove null bytes that could corrupt downstream text processing."""
        return v.replace("\x00", "")


# ---------------------------------------------------------------------------
# /query
# ---------------------------------------------------------------------------

class QueryRequest(BaseModel):
    """Body for POST /query."""

    question: str = Field(
        ...,
        min_length=1,
        max_length=2_000,   # Prevents prompt-inflation attacks
        description="Natural language question about the logs (max 2 000 chars)",
    )
    filter_anomalies_only: bool = Field(
        False,
        description="When True, restrict retrieval to anomalous log chunks only",
    )
    upload_id: str | None = Field(
        None,
        max_length=80,
        description="Optional upload id to restrict the query to one ingested log",
    )
    top_k: int = Field(5, ge=1, le=20, description="Number of chunks to retrieve")

    @field_validator("question")
    @classmethod
    def strip_control_chars(cls, v: str) -> str:
        """
        Remove ASCII control characters (except newline/tab) from the question.

        This is a first-line defence against prompt-injection payloads that
        embed hidden instructions using control characters or null bytes.
        """
        cleaned = "".join(
            c for c in v
            if c >= " " or c in ("\n", "\t", "\r")
        )
        return cleaned.strip()


class QueryResponse(BaseModel):
    """Response from POST /query."""
    answer: str
    sources: list[dict[str, Any]]
    retrieval_ms: int
    llm_ms: int


# ---------------------------------------------------------------------------
# /anomalies
# ---------------------------------------------------------------------------

class AnomalyEntry(BaseModel):
    """A single anomalous log entry returned by GET /anomalies."""
    id: str
    document: str
    is_anomaly: bool
    anomaly_score: float
    metadata: dict[str, Any] = {}


class AnomalyListResponse(BaseModel):
    """Response from GET /anomalies."""
    items: list[AnomalyEntry]
    total: int
    offset: int
    limit: int


class AnomalySummaryResponse(BaseModel):
    """Response from GET /anomalies/summary."""
    total_logs: int
    total_anomalies: int
    anomaly_rate: float          # Ratio 0.0–1.0 (NOT a percentage)
    status_code_breakdown: dict[str, int] = {}
    top_suspicious_ips: list[dict[str, Any]] = []


# ---------------------------------------------------------------------------
# /health
# ---------------------------------------------------------------------------

class HealthResponse(BaseModel):
    """Response from GET /health."""
    status: str
    chroma_docs: int
    model: str
    embedding_model: Optional[str] = None
