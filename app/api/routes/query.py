"""
POST /query — natural language querying of the log vector store.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.logger import get_logger
from app.core.rate_limit import query_limiter
from app.models.query_models import QueryRequest, QueryResponse
from app.services import rag_chain

logger = get_logger(__name__)
router = APIRouter(prefix="/query", tags=["query"])


@router.post(
    "",
    response_model=QueryResponse,
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(query_limiter)],
)
def query_logs(body: QueryRequest) -> QueryResponse:
    """
    Run a natural language query against the ingested log data using RAG.

    - *filter_anomalies_only*: restrict retrieval to anomalous log chunks.
    - *top_k*: number of context chunks to retrieve (1–20).

    **Note:** this endpoint is synchronous (`def`, not `async def`) so
    FastAPI runs it in a thread-pool worker automatically, preventing the
    LLM inference from blocking the async event loop.

    Rate-limited to 20 requests per minute per IP.
    """
    # Input is already validated and sanitized by the QueryRequest Pydantic model
    # (max_length=2000, control-char stripping). We do one final guard here.
    question = body.question.strip()
    if not question:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Question must not be empty after stripping whitespace.",
        )

    logger.info(
        f"Query received: '{question[:80]}' "
        f"(top_k={body.top_k}, anomalies_only={body.filter_anomalies_only})"
    )

    result = rag_chain.query(
        question=question,
        top_k=body.top_k,
        filter_anomalies_only=body.filter_anomalies_only,
    )

    return QueryResponse(
        answer=result["answer"],
        sources=result["source_chunks"],
        retrieval_ms=result["retrieval_time_ms"],
        llm_ms=result["llm_time_ms"],
    )
