# AI Security Log Analyst

**MSc Final Project — Technological University of the Shannon (TUS)**
**Student: Nitish Shankar Mudaliar · A00336067**
**Programme: MSc Software Design with AI — Work Placement**
**Supervisor: Peter Vargovcik**

A locally-run, privacy-preserving security-log analysis platform combining
Retrieval-Augmented Generation (RAG) with unsupervised anomaly detection.
Upload log files, ask natural-language questions, and surface unusual activity
— all without data leaving your machine.

---

## Table of Contents

1. [Features](#features)
2. [Architecture Overview](#architecture-overview)
3. [Tech Stack](#tech-stack)
4. [Project Structure](#project-structure)
5. [Prerequisites](#prerequisites)
6. [Installation](#installation)
7. [Running the Application](#running-the-application)
8. [API Reference](#api-reference)
9. [Frontend](#frontend)
10. [Configuration](#configuration)
11. [Testing](#testing)
12. [Known Issues & Fixes Applied](#known-issues--fixes-applied)

---

## Features

- **Log ingestion** — upload `.log` / `.txt` files or paste raw log text via the UI
- **RAG querying** — ask plain-English questions; the LLM answers from retrieved log context
- **Anomaly detection** — Isolation Forest flags statistically unusual log entries
- **Severity classification** — High / Medium / Low badges based on anomaly score
- **Paginated anomaly table** — browse all flagged entries with server-side pagination and score filter
- **Live health badge** — header shows backend connectivity in real-time
- **Animated stats bar** — count-up animation on ingested logs, anomalies, and queries
- **Fully offline** — no HuggingFace network calls; all AI runs locally via Ollama

---

## Architecture Overview

```
Browser (React SPA)
        │
        │  HTTP  (Vite proxy in dev / same-origin in prod)
        ▼
FastAPI  :8000
   ├── POST /ingest          — parse → detect anomalies → chunk → embed → store
   ├── POST /ingest/text     — same pipeline for raw text
   ├── POST /query           — RAG: retrieve chunks → Ollama LLM → answer
   ├── GET  /anomalies       — paginated anomaly list from ChromaDB
   ├── GET  /anomalies/summary
   └── GET  /health
        │
        ├── ChromaDB  (PersistentClient, ./data/chroma_db/)
        │        stores embeddings + metadata, supports anomaly filters
        │
        ├── SentenceTransformers  all-MiniLM-L6-v2  (384-dim, fully offline)
        │        encodes chunks for vector similarity search
        │
        ├── Ollama  (llama3.2 or configurable)
        │        local LLM for answer generation
        │
        └── scikit-learn  IsolationForest
                 unsupervised anomaly detection on log feature vectors
```

---

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend | React 18 + Vite 5, custom CSS design system (no component library) |
| Backend | FastAPI 0.111 + Uvicorn (Python 3.11+) |
| Vector DB | ChromaDB (local PersistentClient, no server required) |
| Embeddings | `sentence-transformers` — `all-MiniLM-L6-v2` (384 dim, offline) |
| LLM | Ollama (`llama3.2` default, fully configurable) |
| Anomaly detection | scikit-learn `IsolationForest` |
| Configuration | `pydantic-settings` with `.env` file support |
| Testing | pytest + pytest-asyncio + httpx `AsyncClient` |

---

## Project Structure

```
AI Security Log Analyst/
├── app/
│   ├── api/
│   │   └── routes/
│   │       ├── ingest.py        # POST /ingest, POST /ingest/text
│   │       ├── query.py         # POST /query
│   │       └── anomaly.py       # GET /anomalies, GET /anomalies/summary
│   ├── core/
│   │   ├── config.py            # pydantic-settings (env vars / .env)
│   │   └── logger.py            # structured logging
│   ├── models/
│   │   ├── log_entry.py         # LogEntry dataclass
│   │   └── query_models.py      # Pydantic request/response schemas
│   ├── services/
│   │   ├── embedder.py          # SentenceTransformer singleton (offline)
│   │   ├── vector_store.py      # ChromaDB read/write operations
│   │   ├── rag_chain.py         # retrieval + Ollama prompt chain
│   │   ├── anomaly_detector.py  # IsolationForest wrapper + persistence
│   │   └── ingestion.py         # chunking helpers
│   ├── utils/
│   │   └── log_parser.py        # multi-format regex log parser
│   └── main.py                  # FastAPI app factory + lifespan startup
│
├── frontend/
│   ├── src/
│   │   ├── api.js               # fetch wrappers for all backend endpoints
│   │   ├── App.jsx              # root component, health polling, toast state
│   │   ├── index.css            # v2 design system (violet / near-black / glassmorphism)
│   │   ├── main.jsx             # React 18 createRoot entry point
│   │   ├── components/
│   │   │   ├── Header.jsx       # sticky header with logo + online/offline badge
│   │   │   ├── StatsBar.jsx     # 4-column animated stats (count-up animation)
│   │   │   ├── UploadCard.jsx   # file drag-drop + raw text ingest card
│   │   │   ├── QueryCard.jsx    # query input, example chips, answer + sources
│   │   │   ├── AnomalyTable.jsx # paginated table with severity badges
│   │   │   └── ToastContainer.jsx  # auto-dismiss notification stack
│   │   └── hooks/
│   │       ├── useCountUp.js    # rAF-based number animation hook
│   │       └── useMouseGlow.js  # CSS var --mx/--my for radial border glow
│   ├── index.html               # Vite entry HTML
│   ├── vite.config.js           # dev proxy config + build output settings
│   └── package.json
│
├── data/
│   ├── raw_logs/                # sample .log files (gitignored)
│   ├── chroma_db/               # ChromaDB persistence (gitignored)
│   └── models/                  # trained IsolationForest .pkl (gitignored)
│
├── tests/
│   ├── test_api.py              # API endpoint integration tests
│   ├── test_anomaly.py          # IsolationForest unit tests
│   ├── test_ingestion.py        # log parsing and chunking tests
│   └── test_rag_chain.py        # RAG retrieval tests
│
├── scripts/
│   ├── generate_sample_logs.py  # generate synthetic Apache access.log data
│   ├── seed_vector_db.py        # pre-ingest sample logs into ChromaDB
│   └── test_rag.py              # quick manual RAG smoke-test
│
├── .env                         # local overrides (gitignored)
├── .gitignore
├── requirements.txt
└── README.md
```

---

## Prerequisites

| Requirement | Minimum version | Notes |
|---|---|---|
| Python | 3.11 | 3.13 tested and confirmed working |
| Node.js | 18 | for the Vite frontend build |
| Ollama | latest | https://ollama.com — for local LLM inference |
| `llama3.2` model | — | `ollama pull llama3.2` |
| `all-MiniLM-L6-v2` | — | cached locally on first run (see below) |

### Pre-cache the embedding model (one-time, requires internet)

The application runs fully offline after this step:

```bash
python - <<'EOF'
from sentence_transformers import SentenceTransformer
SentenceTransformer("all-MiniLM-L6-v2")
print("Model cached successfully.")
EOF
```

The model is downloaded to `~/.cache/huggingface/hub/`.
After this step the app sets `HF_HUB_OFFLINE=1` on startup so no further
network calls are made.

---

## Installation

### 1 — Clone the repository

```bash
git clone <repo-url>
cd "AI Security Log Analyst"
```

### 2 — Python virtual environment

```bash
python -m venv .venv

# Activate — Windows
.venv\Scripts\activate
# Activate — macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt
```

### 3 — Frontend (production build)

```bash
cd frontend
npm install
npm run build       # outputs to frontend/dist/ — served by FastAPI
cd ..
```

> For **development** run `npm run dev` in `frontend/` (port 5173) alongside
> the backend. The Vite dev server proxies `/ingest`, `/query`, `/anomalies`,
> and `/health` to `localhost:8000` automatically.

---

## Running the Application

### 1 — Start Ollama (if not already running as a system service)

```bash
ollama serve
```

### 2 — Start the FastAPI backend

```bash
# Windows with Python 3.13 system installation
C:\Python313\python.exe -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# All platforms (virtual env activated)
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Open **http://localhost:8000** in your browser.

- The root path `/` redirects to the React build at `/app/index.html`.
- Interactive API docs: **http://localhost:8000/docs** (Swagger UI)
- Alternative docs: **http://localhost:8000/redoc**

> **Note:** Avoid `--reload` in production. See [Known Issues](#1--huggingface-async-client-crash-after---reload-fixed).

---

## API Reference

### `GET /health`

Returns backend status and currently loaded model names.

```json
{
  "status": "ok",
  "chroma_docs": 1234,
  "model": "llama3.2",
  "embedding_model": "all-MiniLM-L6-v2"
}
```

---

### `POST /ingest`

Upload a log file via multipart form data (field name: `file`).

- **Accepted extensions:** `.log`, `.txt`
- **Max file size:** 10 MB

**Response:**

```json
{
  "ingested_lines": 512,
  "chunks_stored": 48,
  "anomalies_found": 7,
  "time_ms": 843
}
```

---

### `POST /ingest/text`

Ingest raw log text from the JSON request body.

**Request:**
```json
{ "text": "192.168.1.1 - - [01/Jan/2025:00:00:01 +0000] \"GET /admin HTTP/1.1\" 403 512" }
```

Response schema is the same as `POST /ingest`.

---

### `POST /query`

Ask a natural-language question about the ingested logs.

**Request:**
```json
{
  "question": "Which IP addresses attempted the most failed logins?",
  "top_k": 5,
  "filter_anomalies_only": false
}
```

**Response:**
```json
{
  "answer": "Based on the logs, 192.168.99.5 made 37 failed login attempts…",
  "sources": ["<chunk 1>", "<chunk 2>"],
  "retrieval_ms": 42,
  "llm_ms": 1280
}
```

| Field | Type | Default | Description |
|---|---|---|---|
| `question` | string | required | Natural-language query |
| `top_k` | int | 5 | Context chunks to retrieve (1–20) |
| `filter_anomalies_only` | bool | false | Restrict retrieval to anomalous chunks |

---

### `GET /anomalies`

Paginated list of log entries flagged as anomalies.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `limit` | int | 50 | Results per page (1–200) |
| `offset` | int | 0 | Pagination offset |
| `min_score` | float | 0.0 | Minimum absolute anomaly score |

---

### `GET /anomalies/summary`

Returns aggregate statistics: total logs ingested, anomaly count, anomaly rate (%),
HTTP status code breakdown, and top-10 suspicious IP addresses.

---

## Frontend

The React 18 SPA is built with Vite 5 and served as static files by FastAPI.

### Design System (`frontend/src/index.css`)

The UI uses a bespoke dark design system with a deep-violet / near-black palette:

| Token | Value | Purpose |
|---|---|---|
| `--bg` | `#04020a` | Page background |
| `--violet` | `#8b5cf6` | Primary brand colour |
| `--violet-hi` | `#a78bfa` | Highlights, hover states |
| `--violet-lo` | `#5b21b6` | Button gradient end |
| `--surface-1` | `rgba(255,255,255,0.028)` | Card backgrounds (level 1) |
| `--surface-2` | `rgba(255,255,255,0.055)` | Elevated surfaces (level 2) |
| `--surface-3` | `rgba(255,255,255,0.08)` | Interactive hover states |
| `--text-1` | `#f1eeff` | Primary text |
| `--text-2` | `#c4b8e8` | Secondary text |
| `--text-3` | `#7c6fa0` | Muted / label text |
| `--danger` | `#f87171` | High-severity alerts |
| `--warning` | `#fbbf24` | Medium-severity alerts |
| `--success` | `#34d399` | Success states, low severity |

Key visual effects:
- **Aurora background** — animated multi-ellipse radial gradient via `body::before` (20 s loop)
- **Star noise** — 4-layer 1 px radial-gradient dot field via `body::after`
- **Mouse-tracked border glow** — `--mx`/`--my` CSS custom properties on `.card::before` update on `mousemove`
- **Count-up animation** — `requestAnimationFrame` with cubic ease-out in `useCountUp`
- **Fade-up entrances** — `@keyframes fade-up` on cards and answer panels
- **Online badge ping** — CSS `@keyframes ping` ripple on the status dot

### Components

| Component | Description |
|---|---|
| `Header` | Sticky blur-backdrop header. Shield SVG logo. Live Online/Offline badge with ping animation. |
| `StatsBar` | 4-column CSS grid. Animated count-up numbers (logs ingested, anomalies, queries, model status). |
| `UploadCard` | File drag-and-drop (`.log`, `.txt`) or raw text paste. File/Text mode toggle. Spinner during upload. |
| `QueryCard` | Query text input with 4 clickable example chips. Ctrl+Enter submit. Collapsible RAG sources panel. |
| `AnomalyTable` | Paginated anomaly list (20/page). Min-score filter. High/Medium/Low severity badges with glow dots. |
| `ToastContainer` | Fixed bottom-right stack. Success/error/info variants with left-border colour indicator. Auto-dismiss (4 s). |

---

## Configuration

All values can be overridden by environment variable or `.env` file in the project root.

| Variable | Default | Description |
|---|---|---|
| `CHROMA_PERSIST_DIR` | `./data/chroma_db` | ChromaDB on-disk storage directory |
| `CHROMA_COLLECTION_NAME` | `security_logs` | Collection name inside ChromaDB |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama API base URL (http/https only — SSRF guard) |
| `OLLAMA_MODEL` | `llama3.2` | Ollama model to use for generation |
| `EMBEDDING_MODEL` | `all-MiniLM-L6-v2` | SentenceTransformer model identifier |
| `RAG_TOP_K` | `5` | Number of chunks retrieved per query |
| `ANOMALY_CONTAMINATION` | `0.05` | Expected anomaly fraction (IsolationForest) |
| `ANOMALY_MODEL_PATH` | `./data/models/isolation_forest.pkl` | Saved model path |
| `MAX_CHUNK_SIZE` | `500` | Maximum characters per log chunk |
| `CHUNK_OVERLAP` | `50` | Overlap characters between consecutive chunks |
| `CORS_ORIGINS` | `*` | Comma-separated allowed origins (use explicit list in production) |
| `LOG_LEVEL` | `INFO` | Python logging level |

**Example `.env`:**

```ini
OLLAMA_MODEL=llama3.2:3b
CORS_ORIGINS=http://localhost:5173,http://localhost:8000
LOG_LEVEL=DEBUG
RAG_TOP_K=8
```

---

## Testing

```bash
# Activate virtual environment first, then:

# All tests
pytest

# Individual suites
pytest tests/test_api.py           # API endpoint integration tests
pytest tests/test_anomaly.py       # IsolationForest unit tests
pytest tests/test_ingestion.py     # log parsing and chunking
pytest tests/test_rag_chain.py     # RAG retrieval pipeline

# With coverage report
pytest --cov=app --cov-report=html
open htmlcov/index.html            # view coverage report
```

---

## Known Issues & Fixes Applied

### 1 — HuggingFace async client crash after `--reload` (fixed)

**Symptom:** `POST /ingest` returned HTTP 500. Server log showed:
```
ERROR: Cannot send a request, as the client has been closed.
```

**Root cause:** Uvicorn's `--reload` hot-reload restarts the Python worker
process but `huggingface_hub` initialised its internal async `httpx` client
bound to the original event loop. After reload the stale client raised this
error on every embedding request.

**Fix applied:** `app/main.py` now sets all five HuggingFace offline/telemetry
environment variables via **direct `os.environ[...]` assignment** (not
`os.environ.setdefault`) as the very first code before any other import,
preventing the `httpx` client from ever being created:

```python
import os
os.environ["HF_HUB_OFFLINE"]           = "1"
os.environ["TRANSFORMERS_OFFLINE"]      = "1"
os.environ["HF_DATASETS_OFFLINE"]       = "1"
os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
os.environ["TOKENIZERS_PARALLELISM"]    = "false"
```

The same assignments are mirrored in `app/services/embedder.py` as a secondary
guard for isolated-module testing.

---

### 2 — Frontend ingest route mismatch (fixed)

**Symptom:** Uploading a file showed "Ingest failed" toast in the old static UI.

**Root cause:** The original `app.js` called `POST /ingest/file`, but the
FastAPI route is registered as `@router.post("")` with `prefix="/ingest"`,
making the correct path `POST /ingest`.

**Fix applied:** `frontend/src/api.js` calls `POST /ingest` (no trailing path segment).

---

### 3 — CORS wildcard + credentials conflict (documented)

FastAPI's `CORSMiddleware` rejects `allow_origins=["*"]` combined with
`allow_credentials=True` (browsers reject the response). `app/main.py` detects
the wildcard and disables credentials automatically:

```python
wildcard = raw_origins == ["*"]
app.add_middleware(CORSMiddleware, ..., allow_credentials=not wildcard)
```

For production, set `CORS_ORIGINS` to a comma-separated list of explicit origins.

---

### 4 — Git push over corporate SSL proxy

If your network intercepts HTTPS with a custom certificate:

```bash
git -c http.sslVerify=false push origin main
```

---

### 5 — React frontend redesign (v2)

The original teal-themed static HTML/CSS/JS frontend was fully replaced with a
React 18 + Vite 5 SPA. Key changes:

- Deep-violet / near-black colour system (`--bg: #04020a`, `--violet: #8b5cf6`)
- Glassmorphism cards with animated mouse-tracked radial border glow
- Aurora animated gradient background + star noise overlay
- Count-up animated statistics bar
- Drag-and-drop file upload with live feedback
- Collapsible RAG source citations in the query panel
- Auto-dismiss toast notification stack
- Fully responsive layout (breakpoints at 1024 px and 640 px)
- React build output to `frontend/dist/` served by FastAPI at `/app`
