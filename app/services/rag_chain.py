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

Security notes:
  - User question is sanitized by the Pydantic model (QueryRequest) before
    reaching this module (control chars stripped, max 2 000 chars).
  - The prompt template uses a strict "answer only from the logs" instruction
    to reduce the attack surface of prompt-injection attempts.
  - The LLM instance is created once per settings combination (cached) under
    a thread lock to prevent duplicate initialisation under concurrent load.
  - Ollama reachability is cached for 15 s to avoid adding a round-trip to
    every query.
"""

from __future__ import annotations

import threading
import time
from typing import Any, Dict, List, Optional

from app.core.config import get_settings
from app.core.logger import get_logger
from app.services import vector_store as vs

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Prompt template
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """\
You are a cybersecurity analyst assistant. \
Use ONLY the log excerpts provided below to answer the question. \
Do not speculate beyond the provided data. \
If the answer is not present in the logs, respond with exactly: "Not found in logs."

Log Context:
{context}

Question: {question}

Answer:"""


# ---------------------------------------------------------------------------
# LLM helpers — thread-safe singleton with settings-keyed cache
# ---------------------------------------------------------------------------

_llm_instance = None
_llm_cache_key: tuple | None = None
_llm_lock = threading.Lock()   # prevent double-initialisation under load


def _get_llm():
    """
    Return a cached LangChain Ollama LLM instance (thread-safe).

    The instance is recreated only when settings (base_url / model) change.
    Returns *None* if the library is not available (graceful fallback).
    """
    global _llm_instance, _llm_cache_key
    settings = get_settings()
    cache_key = (settings.ollama_base_url, settings.ollama_model)

    # Fast path: no lock needed when already initialised with the right key
    if _llm_instance is not None and _llm_cache_key == cache_key:
        return _llm_instance

    with _llm_lock:
        # Double-checked locking: re-test inside the lock
        if _llm_instance is not None and _llm_cache_key == cache_key:
            return _llm_instance

        try:
            from langchain_community.llms import Ollama  # noqa: PLC0415
            _llm_instance = Ollama(
                base_url=settings.ollama_base_url,
                model=settings.ollama_model,
                temperature=0.1,  # low temperature → factual, deterministic log analysis
            )
            _llm_cache_key = cache_key
            return _llm_instance
        except ImportError as exc:
            logger.warning(f"langchain_community not available: {exc}")
            return None


# ---------------------------------------------------------------------------
# Ollama reachability — TTL-cached to avoid N+1 HTTP pings per query
# ---------------------------------------------------------------------------

_OLLAMA_TTL: float = 15.0          # seconds before re-checking
_ollama_reachable: Optional[bool] = None
_ollama_checked_at: float = 0.0
_ollama_lock = threading.Lock()


def _is_ollama_reachable() -> bool:
    """
    Return True if the Ollama server is reachable.

    The result is cached for 15 s so we add at most one extra HTTP request
    every 15 s rather than on every query call.
    """
    global _ollama_reachable, _ollama_checked_at

    now = time.monotonic()
    if _ollama_reachable is not None and (now - _ollama_checked_at) < _OLLAMA_TTL:
        return _ollama_reachable

    with _ollama_lock:
        # Double-checked: another thread may have refreshed while we waited
        now = time.monotonic()
        if _ollama_reachable is not None and (now - _ollama_checked_at) < _OLLAMA_TTL:
            return _ollama_reachable

        import httpx  # noqa: PLC0415
        settings = get_settings()
        try:
            r = httpx.get(f"{settings.ollama_base_url}/api/tags", timeout=3.0)
            _ollama_reachable = r.status_code == 200
        except Exception:  # noqa: BLE001
            _ollama_reachable = False

        _ollama_checked_at = time.monotonic()
        return _ollama_reachable


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

    **Threading:** this function is synchronous and CPU/IO-bound (embedding
    inference + optional LLM call).  The route handler (`query.py`) declares
    it as a plain `def` endpoint so FastAPI runs it in a thread-pool worker
    automatically, keeping the async event loop free.

    Args:
        question:              Sanitized natural language question.
        top_k:                 Number of context chunks to retrieve.
                               Defaults to RAG_TOP_K from config.
        filter_anomalies_only: If True, restrict retrieval to anomalous docs.

    Returns:
        {
            "answer":              str,
            "source_chunks":       List[dict],
            "retrieval_time_ms":   int,
            "llm_time_ms":         int,
            "error":               str | None,
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

    # Deduplicate identical chunks (e.g. same file ingested multiple times)
    deduped_results: List[Dict[str, Any]] = []
    seen_docs: Dict[str, int] = {}
    for result in results:
        document = result.get("document") or ""
        existing_idx = seen_docs.get(document)
        if existing_idx is None:
            seen_docs[document] = len(deduped_results)
            deduped_results.append(result)
            continue

        existing_meta = deduped_results[existing_idx].get("metadata") or {}
        new_meta = result.get("metadata") or {}
        if not existing_meta.get("source_name") and new_meta.get("source_name"):
            deduped_results[existing_idx] = result
    results = deduped_results

    source_chunks: List[str] = [r["document"] for r in results]
    source_refs: List[Dict[str, Any]] = []

    for idx, result in enumerate(results, start=1):
        metadata = result.get("metadata") or {}
        document = result.get("document") or ""
        source_name = metadata.get("source_name") or "Unknown upload"
        source_refs.append({
            "source_name": source_name,
            "upload_id":   metadata.get("upload_id") or "",
            "chunk_index": metadata.get("chunk_index"),
            "source_ip":   metadata.get("source_ip") or "",
            "status_code": metadata.get("status_code") or 0,
            "path":        metadata.get("path") or "",
            "distance":    result.get("distance"),
            "preview":     document[:400],
        })
        source_chunks[idx - 1] = (
            f"[Source: {source_name}, chunk {metadata.get('chunk_index', idx)}]\n{document}"
        )

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

    if not _is_ollama_reachable():
        logger.warning("Ollama is not reachable — returning context-only response.")
        llm_ms = int((time.perf_counter() - t_llm_start) * 1000)
        return {
            "answer": (
                "LLM unavailable (Ollama not running). "
                "Retrieved context shown in sources."
            ),
            "source_chunks": source_refs,
            "retrieval_time_ms": retrieval_ms,
            "llm_time_ms": llm_ms,
            "error": "Ollama not reachable",
        }

    llm = _get_llm()
    if llm is None:
        return {
            "answer": "LLM library not available.",
            "source_chunks": source_refs,
            "retrieval_time_ms": retrieval_ms,
            "llm_time_ms": 0,
            "error": "langchain_community unavailable",
        }

    try:
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
        "source_chunks": source_refs,
        "retrieval_time_ms": retrieval_ms,
        "llm_time_ms": llm_ms,
        "error": None,
    }


def build_rag_chain():
    """
    Return a LangChain LCEL chain object for advanced usage.
    Falls back to None if dependencies are missing.
    """
    try:
        from langchain_core.output_parsers import StrOutputParser  # noqa: PLC0415
        from langchain_core.prompts import PromptTemplate  # noqa: PLC0415
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
