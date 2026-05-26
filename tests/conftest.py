"""
pytest configuration and shared fixtures.

Key fixtures (session-scoped, autouse):

  mock_embedder
    Replaces the real SentenceTransformer with a deterministic hash-based
    function. Tests run fully offline — no HuggingFace download needed.

  isolated_chroma
    Points ChromaDB at a fresh temp directory. Tests never touch the
    production data/chroma_db folder.
"""

from __future__ import annotations

import hashlib
import math
import os
from typing import List
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Deterministic mock embedding (384 dimensions, unit-normalised)
# ---------------------------------------------------------------------------

_DIM = 384


def _fake_embed_text(text: str) -> List[float]:
    """SHA-256 hash → deterministic 384-dim unit vector."""
    digest = hashlib.sha256(text.encode()).digest()  # 32 bytes
    raw = [(digest[i % len(digest)] - 128) / 128.0 for i in range(_DIM)]
    magnitude = math.sqrt(sum(v * v for v in raw)) or 1.0
    return [v / magnitude for v in raw]


def _fake_embed_batch(texts: List[str]) -> List[List[float]]:
    return [_fake_embed_text(t) for t in texts]


def _fake_embed_single(text: str) -> List[float]:
    return _fake_embed_text(text)


# ---------------------------------------------------------------------------
# Session-scoped fixture: patch the embedder
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session", autouse=True)
def mock_embedder():
    """
    Swap the real SentenceTransformer for a hash-based embedder so all
    tests run offline without downloading any model.
    """
    with patch("app.services.embedder.embed",        side_effect=_fake_embed_batch), \
         patch("app.services.embedder.embed_single",  side_effect=_fake_embed_single), \
         patch("app.services.embedder.preload_model", return_value=None), \
         patch("app.services.embedder.get_embedding_dimension", return_value=_DIM):
        yield


# ---------------------------------------------------------------------------
# Session-scoped fixture: isolated ChromaDB via env vars + settings reset
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session", autouse=True)
def isolated_chroma(tmp_path_factory):
    """
    Use a fresh temp directory for ChromaDB during the test session.
    Achieved by overriding env vars and clearing the lru_cache on Settings.
    """
    tmp_dir = str(tmp_path_factory.mktemp("chroma_test"))

    env_overrides = {
        "CHROMA_PERSIST_DIR": tmp_dir,
        "CHROMA_COLLECTION_NAME": "test_logs",
    }

    with patch.dict(os.environ, env_overrides):
        # Clear the lru_cache so get_settings() re-reads env vars
        from app.core.config import get_settings
        get_settings.cache_clear()

        # Reset the ChromaDB client singleton so it picks up the new path
        import app.services.vector_store as vs
        vs._client = None

        # Also reset the embedder singleton (already mocked above)
        import app.services.embedder as emb
        emb._model = None

        yield tmp_dir

        # Cleanup after session
        vs._client = None
        get_settings.cache_clear()
