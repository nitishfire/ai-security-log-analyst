"""
Request / Response Pydantic schemas for the REST API.
"""

from typing import Any, Optional
from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# /ingest
# ---------------------------------------------------------------------------

class IngestResponse(BaseModel):
    """Response from POST /ingest or POST /ingest/text."""
    ingested_lines: int
    chunks_stored: int
    anomalies_found: int
    time_ms: int


class IngestTextRequest(BaseModel):
    """Body for POST /ingest/text."""
    text: str = Field(..., description="Raw log text to ingest")


# ---------------------------------------------------------------------------
# /query
# ---------------------------------------------------------------------------

class QueryRequest(BaseModel):
    """Body for POST /query."""
    question: str = Field(..., description="Natural language question about the logs")
    filter_anomalies_only: bool = Field(
        False,
        description="When True, restrict retrieval to anomalous log chunks only",
    )
    top_k: int = Field(5, ge=1, le=20, description="Number of chunks to retrieve")


class QueryResponse(BaseModel):
    """Response from POST /query."""
    answer: str
    sources: list[str]
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
    anomaly_rate: float
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
