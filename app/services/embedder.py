"""
SentenceTransformer embedding service.

Wraps the HuggingFace sentence-transformers library and exposes
a simple interface for batch and single-text embedding.
The model is loaded once (singleton) and reused across calls.
"""

from __future__ import annotations

import os
import time
from typing import List, Optional

from app.core.config import get_settings
from app.core.logger import get_logger

# Force HuggingFace Hub to use the local cache without phoning home.
# This prevents "Cannot send a request, as the client has been closed"
# errors when the corporate SSL proxy blocks outbound HTTPS to hf.co.
# The model must already be present in ~/.cache/huggingface/hub/.
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

logger = get_logger(__name__)

# Module-level singleton — populated on first call to _get_model()
_model = None
_model_name: Optional[str] = None


def _get_model():
    """Load (or return cached) SentenceTransformer model."""
    global _model, _model_name

    settings = get_settings()
    requested_model = settings.embedding_model

    if _model is not None and _model_name == requested_model:
        return _model

    # Lazy import — heavy library, only loaded when needed
    from sentence_transformers import SentenceTransformer  # noqa: PLC0415

    logger.info(f"Loading embedding model: {requested_model}")
    t0 = time.perf_counter()
    _model = SentenceTransformer(requested_model)
    _model_name = requested_model
    elapsed = (time.perf_counter() - t0) * 1000
    logger.info(f"Embedding model loaded in {elapsed:.1f} ms")

    return _model


def embed(texts: List[str]) -> List[List[float]]:
    """
    Embed a batch of texts.

    Args:
        texts: List of strings to embed.

    Returns:
        List of embedding vectors (each a list of floats).
    """
    if not texts:
        return []

    model = _get_model()
    t0 = time.perf_counter()
    embeddings = model.encode(texts, show_progress_bar=False, convert_to_numpy=True)
    elapsed_ms = (time.perf_counter() - t0) * 1000

    logger.debug(
        f"Embedded {len(texts)} texts in {elapsed_ms:.1f} ms "
        f"({elapsed_ms / len(texts):.2f} ms/text)"
    )
    return embeddings.tolist()


def embed_single(text: str) -> List[float]:
    """
    Embed a single text string.

    Args:
        text: String to embed.

    Returns:
        Embedding vector as a list of floats.
    """
    results = embed([text])
    return results[0] if results else []


def get_embedding_dimension() -> int:
    """Return the dimensionality of the current model's output vectors."""
    model = _get_model()
    return model.get_sentence_embedding_dimension()


def preload_model() -> None:
    """
    Explicitly load the embedding model (e.g. on application startup).
    Call this to avoid a cold-start delay on the first request.
    """
    _get_model()
