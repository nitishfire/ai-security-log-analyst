"""
LangChain RAG pipeline for natural language querying of security logs.

Architecture:
  1. Retriever  — wraps vector_store.similarity_search for top-K chunks
  2. Prompt     — cybersecurity analyst persona with strict context-only policy
  3. LLM        — Ollama (local LLaMA 3.2); graceful fallback if unavailable
  4. Parser     — StrOutputParser → plain string answer

Usage:
    from app.services.rag_chain import query
    result = query("Show me all failed login attempts")
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from app.core.config import get_settings
from app.core.logger import get_logger
from app.services import vector_store as vs

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Prompt template
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """You are a cybersecurity analyst assistant. \
Use ONLY the following log excerpts to answer the question. \
If the answer is not in the logs, say "Not found in logs."

Log Context:
{context}

Question: {question}

Answer:"""


# ---------------------------------------------------------------------------
# LLM helpers
# ---------------------------------------------------------------------------

def _get_llm():
    """
    Return a LangChain Ollama LLM instance.
    Returns *None* if the library is not available (graceful fallback).
    """
    settings = get_settings()
    try:
        from langchain_community.llms import Ollama  # noqa: PLC0415
        return Ollama(
            base_url=settings.ollama_base_url,
            model=settings.ollama_model,
            temperature=0.1,  # Low temperature for factual log analysis
        )
    except ImportError as exc:
        logger.warning(f"langchain_community not available: {exc}")
        return None


def _is_ollama_reachable() -> bool:
    """Ping the Ollama server; return True if reachable."""
    import httpx  # noqa: PLC0415
    settings = get_settings()
    try:
        r = httpx.get(f"{settings.ollama_base_url}/api/tags", timeout=3.0)
        return r.status_code == 200
    except Exception:  # noqa: BLE001
        return False


# ---------------------------------------------------------------------------
# Core query function
# ---------------------------------------------------------------------------

def query(
    question: str,
    top_k: Optional[int] = None,
    filter_anomalies_only: bool = False,
) -> Dict[str, Any]:
    """
    Run the full RAG pipeline for *question*.

    Args:
        question:              The natural language question.
        top_k:                 Number of context chunks to retrieve.
                               Defaults to RAG_TOP_K from config.
        filter_anomalies_only: If True, restrict retrieval to anomalous docs.

    Returns:
        {
            "answer":          str,
            "source_chunks":   List[str],
            "retrieval_time_ms": int,
            "llm_time_ms":     int,
            "error":           str | None,
        }
    """
    settings = get_settings()
    k = top_k or settings.rag_top_k

    # ── Retrieval ────────────────────────────────────────────────────────────
    t_retrieval_start = time.perf_counter()
    where_filter: Optional[Dict[str, Any]] = None
    if filter_anomalies_only:
        where_filter = {"is_anomaly": True}

    try:
        results = vs.similarity_search(question, k=k, where=where_filter)
    except Exception as exc:  # noqa: BLE001
        logger.error(f"Retrieval failed: {exc}")
        return {
            "answer": "Retrieval failed — the vector database may be empty or unavailable.",
            "source_chunks": [],
            "retrieval_time_ms": 0,
            "llm_time_ms": 0,
            "error": str(exc),
        }

    retrieval_ms = int((time.perf_counter() - t_retrieval_start) * 1000)
    source_chunks: List[str] = [r["document"] for r in results]

    if not source_chunks:
        return {
            "answer": "Not found in logs.",
            "source_chunks": [],
            "retrieval_time_ms": retrieval_ms,
            "llm_time_ms": 0,
            "error": None,
        }

    context = "\n\n---\n\n".join(source_chunks)
    prompt_text = _SYSTEM_PROMPT.format(context=context, question=question)

    # ── LLM call ─────────────────────────────────────────────────────────────
    t_llm_start = time.perf_counter()

    # Check Ollama availability before attempting inference
    if not _is_ollama_reachable():
        logger.warning("Ollama is not reachable — returning context-only response.")
        llm_ms = int((time.perf_counter() - t_llm_start) * 1000)
        return {
            "answer": (
                "LLM unavailable (Ollama not running). "
                "Retrieved context shown in sources."
            ),
            "source_chunks": source_chunks,
            "retrieval_time_ms": retrieval_ms,
            "llm_time_ms": llm_ms,
            "error": "Ollama not reachable",
        }

    llm = _get_llm()
    if llm is None:
        return {
            "answer": "LLM library not available.",
            "source_chunks": source_chunks,
            "retrieval_time_ms": retrieval_ms,
            "llm_time_ms": 0,
            "error": "langchain_community unavailable",
        }

    try:
        # LangChain v0.2 simple invocation
        answer = llm.invoke(prompt_text)
        if not isinstance(answer, str):
            answer = str(answer)
    except Exception as exc:  # noqa: BLE001
        logger.error(f"LLM inference failed: {exc}")
        answer = f"LLM error: {exc}"

    llm_ms = int((time.perf_counter() - t_llm_start) * 1000)
    logger.info(f"RAG query completed — retrieval={retrieval_ms}ms, llm={llm_ms}ms")

    return {
        "answer": answer.strip(),
        "source_chunks": source_chunks,
        "retrieval_time_ms": retrieval_ms,
        "llm_time_ms": llm_ms,
        "error": None,
    }


def build_rag_chain():
    """
    Return a LangChain LCEL chain object for advanced usage.
    Falls back to None if dependencies are missing.

    The chain: retriever | format_docs | prompt | llm | StrOutputParser
    """
    try:
        from langchain_core.prompts import PromptTemplate  # noqa: PLC0415
        from langchain_core.output_parsers import StrOutputParser  # noqa: PLC0415
        from langchain_core.runnables import RunnablePassthrough  # noqa: PLC0415
    except ImportError as exc:
        logger.warning(f"LangChain core not available for chain building: {exc}")
        return None

    llm = _get_llm()
    if llm is None:
        return None

    prompt = PromptTemplate.from_template(_SYSTEM_PROMPT)

    def retrieve_and_format(q: str) -> str:
        settings = get_settings()
        results = vs.similarity_search(q, k=settings.rag_top_k)
        return "\n\n---\n\n".join(r["document"] for r in results)

    chain = (
        {"context": retrieve_and_format, "question": RunnablePassthrough()}
        | prompt
        | llm
        | StrOutputParser()
    )
    return chain
