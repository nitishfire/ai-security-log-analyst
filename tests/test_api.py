"""
API integration tests using FastAPI TestClient.

Covers:
  - GET  /health
  - POST /ingest/text
  - POST /query
  - GET  /anomalies
  - GET  /anomalies/summary
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture(scope="module")
def client():
    """Create a single TestClient shared across all tests in this module."""
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c


# Sample Apache log text used across multiple tests
SAMPLE_LOGS = "\n".join([
    '192.168.1.10 - - [01/Jun/2024:10:01:00 +0000] "POST /login HTTP/1.1" 401 512 "-" "Mozilla/5.0"',
    '192.168.1.10 - - [01/Jun/2024:10:01:05 +0000] "POST /login HTTP/1.1" 401 512 "-" "Mozilla/5.0"',
    '10.0.0.1 - - [01/Jun/2024:10:02:00 +0000] "GET /admin HTTP/1.1" 403 256 "-" "curl/7.88.1"',
    '192.168.1.20 - - [01/Jun/2024:10:03:00 +0000] "GET / HTTP/1.1" 200 5120 "-" "Mozilla/5.0"',
    '192.168.1.30 - - [01/Jun/2024:10:04:00 +0000] "GET /index.html HTTP/1.1" 200 4096 "-" "Mozilla/5.0"',
    '10.0.0.2 - - [01/Jun/2024:10:05:00 +0000] "GET /wp-login.php HTTP/1.1" 404 128 "-" "sqlmap/1.7"',
    '1.2.3.4 - - [01/Jun/2024:10:06:00 +0000] "GET /../../../../etc/passwd HTTP/1.1" 400 0 "-" "-"',
    '192.168.1.40 - - [01/Jun/2024:10:07:00 +0000] "GET /api/health HTTP/1.1" 200 64 "-" "Go-http-client/1.1"',
])


# ── /health ───────────────────────────────────────────────────────────────────

class TestHealthEndpoint:
    def test_returns_200(self, client):
        r = client.get("/health")
        assert r.status_code == 200

    def test_status_ok(self, client):
        data = client.get("/health").json()
        assert data["status"] == "ok"

    def test_has_chroma_docs_field(self, client):
        data = client.get("/health").json()
        assert "chroma_docs" in data
        assert isinstance(data["chroma_docs"], int)

    def test_has_model_field(self, client):
        data = client.get("/health").json()
        assert "model" in data
        assert isinstance(data["model"], str)


# ── /ingest/text ──────────────────────────────────────────────────────────────

class TestIngestTextEndpoint:
    def test_returns_200(self, client):
        r = client.post("/ingest/text", json={"text": SAMPLE_LOGS})
        assert r.status_code == 200

    def test_ingested_lines_positive(self, client):
        data = client.post("/ingest/text", json={"text": SAMPLE_LOGS}).json()
        assert data["ingested_lines"] > 0

    def test_chunks_stored_positive(self, client):
        data = client.post("/ingest/text", json={"text": SAMPLE_LOGS}).json()
        assert data["chunks_stored"] > 0

    def test_anomalies_found_is_int(self, client):
        data = client.post("/ingest/text", json={"text": SAMPLE_LOGS}).json()
        assert isinstance(data["anomalies_found"], int)

    def test_time_ms_positive(self, client):
        data = client.post("/ingest/text", json={"text": SAMPLE_LOGS}).json()
        assert data["time_ms"] >= 0

    def test_empty_text_returns_422(self, client):
        r = client.post("/ingest/text", json={"text": "# just a comment\n\n"})
        assert r.status_code == 422

    def test_missing_body_returns_422(self, client):
        r = client.post("/ingest/text", json={})
        assert r.status_code == 422


# ── /query ────────────────────────────────────────────────────────────────────

class TestQueryEndpoint:
    @pytest.fixture(autouse=True)
    def ensure_data(self, client):
        """Ensure some data is ingested before running query tests."""
        client.post("/ingest/text", json={"text": SAMPLE_LOGS})

    def test_returns_200(self, client):
        r = client.post("/query", json={"question": "Show me failed login attempts"})
        assert r.status_code == 200

    def test_answer_is_string(self, client):
        data = client.post("/query", json={"question": "Any requests to /admin?"}).json()
        assert isinstance(data["answer"], str)
        assert len(data["answer"]) > 0

    def test_sources_is_list(self, client):
        data = client.post("/query", json={"question": "What IPs had errors?"}).json()
        assert isinstance(data["sources"], list)

    def test_retrieval_ms_present(self, client):
        data = client.post("/query", json={"question": "test"}).json()
        assert "retrieval_ms" in data
        assert isinstance(data["retrieval_ms"], int)

    def test_top_k_respected(self, client):
        data = client.post(
            "/query",
            json={"question": "failed login", "top_k": 2},
        ).json()
        assert len(data["sources"]) <= 2

    def test_empty_question_returns_422(self, client):
        r = client.post("/query", json={"question": "   "})
        assert r.status_code == 422

    def test_filter_anomalies_only_flag(self, client):
        r = client.post(
            "/query",
            json={"question": "anomalous traffic", "filter_anomalies_only": True},
        )
        assert r.status_code == 200


# ── /anomalies ────────────────────────────────────────────────────────────────

class TestAnomaliesEndpoint:
    @pytest.fixture(autouse=True)
    def ensure_data(self, client):
        client.post("/ingest/text", json={"text": SAMPLE_LOGS})

    def test_returns_200(self, client):
        r = client.get("/anomalies")
        assert r.status_code == 200

    def test_response_has_items(self, client):
        data = client.get("/anomalies").json()
        assert "items" in data
        assert isinstance(data["items"], list)

    def test_response_has_pagination_fields(self, client):
        data = client.get("/anomalies").json()
        assert "total"  in data
        assert "offset" in data
        assert "limit"  in data

    def test_limit_param_respected(self, client):
        data = client.get("/anomalies?limit=5").json()
        assert len(data["items"]) <= 5

    def test_offset_param_accepted(self, client):
        r = client.get("/anomalies?offset=1000")
        assert r.status_code == 200


# ── /anomalies/summary ────────────────────────────────────────────────────────

class TestAnomaliesSummaryEndpoint:
    @pytest.fixture(autouse=True)
    def ensure_data(self, client):
        client.post("/ingest/text", json={"text": SAMPLE_LOGS})

    def test_returns_200(self, client):
        r = client.get("/anomalies/summary")
        assert r.status_code == 200

    def test_total_logs_non_negative(self, client):
        data = client.get("/anomalies/summary").json()
        assert data["total_logs"] >= 0

    def test_anomaly_rate_field_present(self, client):
        data = client.get("/anomalies/summary").json()
        assert "anomaly_rate" in data
        assert isinstance(data["anomaly_rate"], (int, float))

    def test_top_suspicious_ips_is_list(self, client):
        data = client.get("/anomalies/summary").json()
        assert isinstance(data["top_suspicious_ips"], list)
