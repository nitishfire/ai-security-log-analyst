"""
POST /query — natural language querying of the log vector store.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from app.core.logger import get_logger
from app.models.query_models import QueryRequest, QueryResponse
from app.services import rag_chain

logger = get_logger(__name__)
router = APIRouter(prefix="/query", tags=["query"])


@router.post("", response_model=QueryResponse, status_code=status.HTTP_200_OK)
async def query_logs(body: QueryRequest) -> QueryResponse:
    """
    Run a natural language query against the ingested log data using RAG.

    - *filter_anomalies_only*: restrict retrieval to anomalous log chunks.
    - *top_k*: number of context chunks to retrieve (1–20).
    """
    if not body.question.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Question must not be empty.",
        )

    logger.info(
        f"Query received: '{body.question[:80]}' "
        f"(top_k={body.top_k}, anomalies_only={body.filter_anomalies_only})"
    )

    result = rag_chain.query(
        question=body.question,
        top_k=body.top_k,
        filter_anomalies_only=body.filter_anomalies_only,
    )

    return QueryResponse(
        answer=result["answer"],
        sources=result["source_chunks"],
        retrieval_ms=result["retrieval_time_ms"],
        llm_ms=result["llm_time_ms"],
    )
