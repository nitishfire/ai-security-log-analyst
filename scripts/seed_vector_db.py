"""
One-shot script: parse sample_access.log → chunk → embed → store in ChromaDB.

Usage:
    python scripts/seed_vector_db.py [--log-file PATH] [--reset]

Options:
    --log-file  Path to the log file (default: data/raw_logs/sample_access.log)
    --reset     Delete the existing collection before seeding
"""

from __future__ import annotations

import argparse
import sys
import time
import uuid
from pathlib import Path

# Project root on path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.config import get_settings
from app.services.ingestion import load_log_file, chunk_logs
from app.services import vector_store as vs


def main(log_file: str, reset: bool) -> None:
    settings = get_settings()
    t_start = time.perf_counter()

    # ── Load and parse ──────────────────────────────────────────────────────
    print(f"[1/4] Parsing log file: {log_file}")
    entries = load_log_file(log_file)
    print(f"      Parsed {len(entries)} log entries.")

    if not entries:
        print("ERROR: No entries parsed. Check the log file format.")
        sys.exit(1)

    # ── Chunk ───────────────────────────────────────────────────────────────
    print(f"[2/4] Chunking (chunk_size={settings.max_chunk_size}, overlap={settings.chunk_overlap})...")
    chunks = chunk_logs(entries, chunk_size=settings.max_chunk_size, overlap=settings.chunk_overlap)
    print(f"      Created {len(chunks)} chunks.")

    # ── Optionally reset collection ─────────────────────────────────────────
    if reset:
        print(f"[2b]  Deleting existing collection '{settings.chroma_collection_name}'...")
        try:
            vs.delete_collection()
        except Exception as e:
            print(f"      (No existing collection to delete: {e})")

    # ── Build metadata ───────────────────────────────────────────────────────
    print("[3/4] Preparing metadata...")
    metadatas = []
    ids = []
    for i, chunk in enumerate(chunks):
        doc_id = str(uuid.uuid4())
        ids.append(doc_id)
        metadatas.append({
            "chunk_index": i,
            "source_file": Path(log_file).name,
            "is_anomaly": False,       # Will be updated after anomaly detection
            "anomaly_score": 0.0,
        })

    # ── Embed and store ──────────────────────────────────────────────────────
    print(f"[4/4] Embedding and storing {len(chunks)} chunks in ChromaDB...")
    print("      (This may take a minute on first run while the model downloads.)")

    # Progress reporting
    batch_size = 50
    for batch_start in range(0, len(chunks), batch_size):
        batch_end = min(batch_start + batch_size, len(chunks))
        pct = batch_end / len(chunks) * 100
        print(f"      Progress: {batch_end}/{len(chunks)} ({pct:.0f}%)", end="\r")

        vs.add_documents(
            chunks=chunks[batch_start:batch_end],
            metadatas=metadatas[batch_start:batch_end],
            ids=ids[batch_start:batch_end],
        )

    print()  # newline after progress

    # ── Summary ──────────────────────────────────────────────────────────────
    stats = vs.get_collection_stats()
    elapsed = (time.perf_counter() - t_start)
    print("\n" + "=" * 50)
    print(f"  Seeding complete in {elapsed:.1f}s")
    print(f"  Collection : {stats['name']}")
    print(f"  Total docs : {stats['count']}")
    print(f"  Log file   : {Path(log_file).name}")
    print(f"  Chunks     : {len(chunks)}")
    print("=" * 50)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed ChromaDB with log embeddings")
    parser.add_argument(
        "--log-file",
        default="data/raw_logs/sample_access.log",
        help="Path to the log file to ingest",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Delete and recreate the ChromaDB collection before seeding",
    )
    args = parser.parse_args()
    main(args.log_file, args.reset)
