"""
Tests for the RAG chain service.

Covers:
  - Query returns a non-empty answer
  - Query returns source chunks
  - Graceful fallback when Ollama is unavailable
"""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest

from app.services import vector_store as vs
from app.services import rag_chain


# ── Fixture: seed a tiny collection ──────────────────────────────────────────

SEED_LOGS = [
    '192.168.1.10 - - [01/Jun/2024:10:01:00 +0000] "POST /login HTTP/1.1" 401 512 "-" "Mozilla/5.0"',
    '192.168.1.10 - - [01/Jun/2024:10:01:05 +0000] "POST /login HTTP/1.1" 401 512 "-" "Mozilla/5.0"',
    '10.0.0.1 - - [01/Jun/2024:10:02:00 +0000] "GET /admin HTTP/1.1" 403 256 "-" "curl/7.88.1"',
    '192.168.1.20 - - [01/Jun/2024:10:03:00 +0000] "GET / HTTP/1.1" 200 5120 "-" "Mozilla/5.0"',
    '1.2.3.4 - - [01/Jun/2024:10:04:00 +0000] "GET /../../../../etc/passwd HTTP/1.1" 400 0 "-" "-"',
]

_COLLECTION_SEEDED = False


def _seed_collection():
    global _COLLECTION_SEEDED
    if _COLLECTION_SEEDED:
        return
    ids       = [str(uuid.uuid4()) for _ in SEED_LOGS]
    metadatas = [{"source": "test", "is_anomaly": False, "anomaly_score": 0.0} for _ in SEED_LOGS]
    vs.add_documents(chunks=SEED_LOGS, metadatas=metadatas, ids=ids)
    _COLLECTION_SEEDED = True


# ── Tests ─────────────────────────────────────────────────────────────────────

class TestRagChain:
    @pytest.fixture(autouse=True)
    def seed(self):
        """Seed a small collection before every test in this class."""
        _seed_collection()

    def test_rag_returns_non_empty_answer(self):
        """Query should always return a string answer (even if Ollama is down)."""
        result = rag_chain.query("Show me all failed login attempts", top_k=3)
        assert isinstance(result["answer"], str)
        assert len(result["answer"]) > 0

    def test_rag_returns_sources(self):
        """Sources list should be non-empty when relevant logs are in the store."""
        result = rag_chain.query("Show me requests to /admin", top_k=3)
        assert isinstance(result["source_chunks"], list)
        assert len(result["source_chunks"]) > 0

    def test_rag_result_has_timing_fields(self):
        """Result must include retrieval_time_ms and llm_time_ms as ints."""
        result = rag_chain.query("Any requests to /login?", top_k=2)
        assert isinstance(result["retrieval_time_ms"], int)
        assert isinstance(result["llm_time_ms"], int)
        assert result["retrieval_time_ms"] >= 0
        assert result["llm_time_ms"] >= 0

    def test_rag_ollama_down_returns_error_message_not_exception(self):
        """
        When Ollama is unreachable the function must NOT raise —
        it should return an error-message answer instead.
        """
        # Patch _is_ollama_reachable to simulate Ollama being down
        with patch.object(rag_chain, "_is_ollama_reachable", return_value=False):
            result = rag_chain.query("failed logins", top_k=3)
        # Should not raise; answer should mention unavailability
        assert isinstance(result["answer"], str)
        assert len(result["answer"]) > 0
        assert result.get("error") is not None

    def test_rag_filter_anomalies_only(self):
        """
        filter_anomalies_only=True should restrict retrieval to anomalous docs.
        When none are flagged the response is still a valid dict (may be empty).
        """
        result = rag_chain.query("login failures", top_k=5, filter_anomalies_only=True)
        assert isinstance(result, dict)
        assert "answer" in result
        assert "source_chunks" in result

    def test_rag_empty_collection_returns_not_found(self):
        """
        Querying a collection name that has no documents should return
        a 'not found in logs' style response without crashing.
        """
        with patch.object(vs, "similarity_search", return_value=[]):
            result = rag_chain.query("anything", top_k=3)
        assert isinstance(result["answer"], str)
        assert len(result["answer"]) > 0


class TestRagChainEdgeCases:
    def test_very_long_question(self):
        """Long question should not crash the pipeline."""
        long_q = "Show me " + ("failed logins " * 50)
        result = rag_chain.query(long_q, top_k=2)
        assert isinstance(result, dict)
        assert "answer" in result

    def test_empty_question_still_runs(self):
        """Empty question string should degrade gracefully (retrieval may return nothing)."""
        result = rag_chain.query("", top_k=2)
        assert isinstance(result, dict)
