"""
FastAPI application entry point.

Startup sequence:
  1. Configure logging
  2. Warm up ChromaDB connection
  3. Preload the embedding model
  4. Load or fit the anomaly detection model (if data exists)

Run locally:
    uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
"""

# ── Offline / no-telemetry env vars ──────────────────────────────────────────
# These MUST be set before *any* HuggingFace import so that the httpx client is
# never initialised in the first place.  Using direct assignment (not setdefault)
# so they can't be overridden by a stale os.environ entry from a previous
# hot-reload cycle.
import os
os.environ["HF_HUB_OFFLINE"]              = "1"   # no hub downloads
os.environ["TRANSFORMERS_OFFLINE"]         = "1"   # no transformers downloads
os.environ["HF_DATASETS_OFFLINE"]          = "1"   # no datasets downloads
os.environ["HF_HUB_DISABLE_TELEMETRY"]    = "1"   # no telemetry HTTP calls
os.environ["TOKENIZERS_PARALLELISM"]       = "false"  # avoid deadlocks in threads
# ─────────────────────────────────────────────────────────────────────────────

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes import anomaly, ingest, query
from app.core.config import get_settings
from app.core.logger import get_logger
from app.models.query_models import HealthResponse
from app.services import embedder as embedder_svc
from app.services import vector_store as vs
from app.services.anomaly_detector import get_detector
from app.services.ingestion import load_log_file

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Lifespan (startup / shutdown)
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Run startup tasks; then yield; then cleanup."""
    settings = get_settings()
    logger.info("=" * 50)
    logger.info("AI Security Log Analyst — starting up")
    logger.info(f"  Embedding model : {settings.embedding_model}")
    logger.info(f"  LLM             : {settings.ollama_model} @ {settings.ollama_base_url}")
    logger.info(f"  ChromaDB        : {settings.chroma_persist_dir}")
    logger.info("=" * 50)

    # 1. Warm up ChromaDB
    try:
        stats = vs.get_collection_stats()
        logger.info(f"ChromaDB ready — collection '{stats['name']}' has {stats['count']} docs")
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"ChromaDB init warning: {exc}")

    # 2. Preload embedding model
    try:
        embedder_svc.preload_model()
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"Embedding model preload warning: {exc}")

    # 3. Load or fit anomaly model
    detector = get_detector()
    sample_log = Path("data/raw_logs/sample_access.log")
    try:
        if Path(settings.anomaly_model_path).exists():
            detector.load_or_fit([])  # will load from disk
        elif sample_log.exists():
            entries = load_log_file(str(sample_log))
            if entries:
                detector.fit(entries)
                logger.info(f"Anomaly model fitted on {len(entries)} sample entries")
        else:
            logger.info("No sample logs found — anomaly model will be fitted on first ingest")
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"Anomaly model init warning: {exc}")

    yield  # ── application is running ──

    logger.info("Shutting down AI Security Log Analyst")


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------

def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="AI Security Log Analyst",
        description=(
            "RAG-powered security log analysis with anomaly detection. "
            "Upload logs, query them in natural language, and surface anomalies."
        ),
        version="1.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )

    # CORS — configured from settings.
    # NOTE: allow_origins=["*"] and allow_credentials=True is an invalid CORS
    # combination (browsers will reject it). When origins is "*" we disable
    # credentials so the wildcard is valid. For production, set CORS_ORIGINS to
    # a comma-separated list of allowed origins and credentials will be enabled.
    raw_origins = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]
    wildcard = raw_origins == ["*"]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=raw_origins,
        allow_credentials=not wildcard,  # credentials require explicit origins
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # API routers
    app.include_router(ingest.router)
    app.include_router(query.router)
    app.include_router(anomaly.router)

    # ── Health check ─────────────────────────────────────────────────────────
    @app.get("/health", response_model=HealthResponse, tags=["system"])
    async def health_check() -> HealthResponse:
        """System health — checks ChromaDB and reports model in use."""
        try:
            stats = vs.get_collection_stats()
            chroma_docs = stats["count"]
        except Exception:  # noqa: BLE001
            chroma_docs = -1

        return HealthResponse(
            status="ok",
            chroma_docs=chroma_docs,
            model=settings.ollama_model,
            embedding_model=settings.embedding_model,
        )

    # ── Root redirect ─────────────────────────────────────────────────────────
    @app.get("/", include_in_schema=False)
    async def root() -> RedirectResponse:
        return RedirectResponse(url="/app/index.html")

    # Serve React build (frontend/dist/).  Mount LAST so API routes take priority.
    # In dev mode the Vite dev server handles this; the built dist/ is for prod.
    react_dist = Path("frontend/dist")
    if react_dist.exists():
        app.mount("/app", StaticFiles(directory=str(react_dist), html=True), name="frontend")

    return app


app = create_app()
