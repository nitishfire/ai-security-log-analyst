"""
Application configuration using pydantic-settings.
All values can be overridden via environment variables or .env file.
"""

from functools import lru_cache
from urllib.parse import urlparse

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Typed settings loaded from environment / .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # ChromaDB
    chroma_persist_dir: str = "./data/chroma_db"
    chroma_collection_name: str = "security_logs"

    # Ollama / LLM
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.2"

    # Embeddings
    embedding_model: str = "all-MiniLM-L6-v2"

    # Logging
    log_level: str = "INFO"

    # API server
    api_host: str = "0.0.0.0"
    api_port: int = 8000

    # Chunking
    max_chunk_size: int = 500
    chunk_overlap: int = 50

    # RAG
    rag_top_k: int = 5

    # Anomaly detection
    anomaly_contamination: float = 0.05
    anomaly_model_path: str = "./data/models/isolation_forest.pkl"

    # CORS
    cors_origins: str = "*"  # Comma-separated list; use "*" for dev only

    # ── Validators ──────────────────────────────────────────────────────────

    @field_validator("ollama_base_url")
    @classmethod
    def validate_ollama_url(cls, v: str) -> str:
        """
        Prevent SSRF: reject non-HTTP(S) schemes for OLLAMA_BASE_URL.

        This blocks ``file://``, ``ftp://``, ``gopher://`` and other schemes
        that could be exploited to read local files or probe internal services.
        Both ``http://`` and ``https://`` are accepted regardless of the target
        host, enabling local, Docker, and remote deployments.
        """
        parsed = urlparse(v)
        if parsed.scheme not in ("http", "https"):
            raise ValueError(
                f"OLLAMA_BASE_URL must use http or https scheme, got: {parsed.scheme!r}"
            )
        return v


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached Settings singleton."""
    return Settings()
