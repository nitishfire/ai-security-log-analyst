"""
Quick manual test for the RAG chain.

1. Seeds 10 representative log entries into ChromaDB
2. Asks three diagnostic questions
3. Prints answers and source chunks

Run:
    python scripts/test_rag.py [--reset]
"""

from __future__ import annotations

import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import argparse

from app.services import vector_store as vs
from app.services.rag_chain import query

# ── 10 representative log lines ──────────────────────────────────────────────
SEED_LOGS = [
    "192.168.1.10 - - [01/Jun/2024:10:01:00 +0000] \"POST /login HTTP/1.1\" 401 512 \"-\" \"Mozilla/5.0\"",
    "192.168.1.10 - - [01/Jun/2024:10:01:05 +0000] \"POST /login HTTP/1.1\" 401 512 \"-\" \"Mozilla/5.0\"",
    "192.168.1.10 - - [01/Jun/2024:10:01:10 +0000] \"POST /login HTTP/1.1\" 401 512 \"-\" \"Mozilla/5.0\"",
    "10.0.0.1 - - [01/Jun/2024:10:02:00 +0000] \"GET /admin HTTP/1.1\" 403 256 \"-\" \"curl/7.88.1\"",
    "10.0.0.1 - - [01/Jun/2024:10:02:30 +0000] \"GET /wp-login.php HTTP/1.1\" 404 128 \"-\" \"sqlmap/1.7\"",
    "192.168.1.20 - - [01/Jun/2024:10:03:00 +0000] \"GET / HTTP/1.1\" 200 5120 \"-\" \"Mozilla/5.0\"",
    "192.168.1.20 - - [01/Jun/2024:10:03:30 +0000] \"GET /index.html HTTP/1.1\" 200 4096 \"-\" \"Mozilla/5.0\"",
    "1.2.3.4 - - [01/Jun/2024:10:04:00 +0000] \"GET /../../../../etc/passwd HTTP/1.1\" 400 0 \"-\" \"-\"",
    "1.2.3.4 - - [01/Jun/2024:10:04:05 +0000] \"POST /login?user=admin'-- HTTP/1.1\" 200 50000000 \"-\" \"Nikto/2.1.6\"",
    "192.168.1.30 - - [01/Jun/2024:10:05:00 +0000] \"GET /api/health HTTP/1.1\" 200 64 \"-\" \"Go-http-client/1.1\"",
]

QUESTIONS = [
    "Show me all failed login attempts",
    "Were there any requests to /admin?",
    "What IP addresses had the most 404 errors?",
]


def seed(reset: bool) -> None:
    if reset:
        print("Deleting existing collection...")
        try:
            vs.delete_collection()
        except Exception:
            pass

    ids = [str(uuid.uuid4()) for _ in SEED_LOGS]
    metadatas = [
        {"source": "test_seed", "is_anomaly": False, "anomaly_score": 0.0}
        for _ in SEED_LOGS
    ]
    print(f"Seeding {len(SEED_LOGS)} log entries into ChromaDB...")
    vs.add_documents(chunks=SEED_LOGS, metadatas=metadatas, ids=ids)
    stats = vs.get_collection_stats()
    print(f"Collection now has {stats['count']} documents.\n")


def main(reset: bool) -> None:
    seed(reset)

    for i, question in enumerate(QUESTIONS, start=1):
        print(f"{'=' * 60}")
        print(f"Q{i}: {question}")
        print("-" * 60)
        result = query(question)
        print(f"Answer:\n{result['answer']}")
        print(f"\nSources ({len(result['source_chunks'])} chunks):")
        for j, chunk in enumerate(result["source_chunks"], start=1):
            print(f"  [{j}] {chunk[:120]}...")
        print(f"\nRetrieval: {result['retrieval_time_ms']}ms | LLM: {result['llm_time_ms']}ms")
        if result.get("error"):
            print(f"  [NOTE] {result['error']}")
        print()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--reset", action="store_true", help="Reset collection before seeding")
    args = parser.parse_args()
    main(args.reset)
