# AI Security Log Analyst

**Student:** Nitish Shankar Mudaliar (A00336067)  
**Supervisor:** Peter Vargovcik  
**Programme:** MSc Software Design with AI — Work Placement  
**Institution:** Technological University of the Shannon (TUS)  
**Placement Period:** 24 May – 23 Aug 2026 (14 weeks)

---

## Project Overview

AI Security Log Analyst is a Retrieval-Augmented Generation (RAG) pipeline that ingests raw security and server logs, indexes them into a local vector database, and enables natural-language querying through a REST API. Instead of manually sifting through thousands of log lines, security analysts can ask plain-English questions such as *"Show me all failed login attempts in the last hour"* or *"Which IPs triggered the most 403 errors?"* and receive context-grounded answers from a locally hosted LLM.

Beyond RAG-based querying, the system runs unsupervised anomaly detection (scikit-learn Isolation Forest) over every ingested batch of logs. Each log entry is scored and flagged if it deviates from normal patterns based on features such as HTTP status codes, byte counts, URL path depth, suspicious path keywords, and per-IP request frequency. Anomaly metadata is stored alongside embeddings in ChromaDB, enabling filtered queries that restrict retrieval to only the most suspicious traffic. A single-page HTML dashboard ties all capabilities together with drag-and-drop upload, a query interface, an anomaly table, and a real-time health indicator.

---

## Architecture Diagram

```
Raw Log Files (.log / .txt)
         │
         ▼
┌─────────────────────┐
│   Log Parser        │  Regex → Apache / Syslog / KV formats
│  (log_parser.py)    │  → normalised LogEntry objects
└─────────┬───────────┘
          │
          ▼
┌─────────────────────┐       ┌──────────────────────┐
│  Anomaly Detector   │──────▶│  Isolation Forest    │
│ (anomaly_detector)  │       │  (scikit-learn)      │
└─────────┬───────────┘       └──────────────────────┘
          │  annotates entries with is_anomaly + score
          ▼
┌─────────────────────┐
│  Ingestion Service  │  chunk_logs() → overlapping text windows
│  (ingestion.py)     │
└─────────┬───────────┘
          │
          ▼
┌─────────────────────┐       ┌──────────────────────┐
│    Embedder         │──────▶│  SentenceTransformer  │
│   (embedder.py)     │       │  all-MiniLM-L6-v2    │
└─────────┬───────────┘       └──────────────────────┘
          │  384-dim vectors
          ▼
┌─────────────────────┐
│    ChromaDB         │  Local persistent vector store
│  (vector_store.py)  │  cosine similarity index
└─────────┬───────────┘
          │
     ┌────┴────┐
     │         │
     ▼         ▼
┌─────────┐  ┌──────────────────────────────────────────┐
│Anomaly  │  │          RAG Chain (rag_chain.py)         │
│Endpoints│  │  similarity_search → top-K chunks        │
│/anomalies│ │  → Prompt template → Ollama LLaMA 3.2   │
└─────────┘  │  → StrOutputParser → answer + sources   │
             └──────────────┬───────────────────────────┘
                            │
                            ▼
              ┌─────────────────────────┐
              │   FastAPI REST API      │
              │   (app/main.py)         │
              │   POST /ingest          │
              │   POST /ingest/text     │
              │   POST /query           │
              │   GET  /anomalies       │
              │   GET  /anomalies/summary│
              │   GET  /health          │
              └──────────┬──────────────┘
                         │
                         ▼
              ┌─────────────────────────┐
              │   Web Dashboard         │
              │   (frontend/)           │
              │   Upload · Query ·      │
              │   Anomaly Table · Stats │
              └─────────────────────────┘
```

---

## Prerequisites

| Tool | Version | Notes |
|------|---------|-------|
| Python | 3.11+ | 3.13 also works |
| Docker | 24+ | For containerised deployment |
| Docker Compose | v2 | Bundled with Docker Desktop |
| Ollama | Latest | For local LLM inference |

Install Ollama from [https://ollama.com](https://ollama.com), then pull the model:
```bash
ollama pull llama3.2
```

---

## Quick Start

```bash
# 1. Clone and enter the project
git clone <repo-url> ai-security-log-analyst
cd ai-security-log-analyst

# 2. Create a virtual environment and install dependencies
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# 3. Copy environment config
cp .env.example .env

# 4. Generate sample logs and seed the vector database
python scripts/generate_sample_logs.py
python scripts/seed_vector_db.py --reset

# 5. Start the API server
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Open **http://localhost:8000** to access the dashboard, or **http://localhost:8000/docs** for the interactive API documentation.

---

## API Reference

### `GET /health`
System health check.

**Response:**
```json
{
  "status": "ok",
  "chroma_docs": 142,
  "model": "llama3.2",
  "embedding_model": "all-MiniLM-L6-v2"
}
```

---

### `POST /ingest`
Upload a `.log` or `.txt` file (multipart form-data). Max 10 MB.

**Request:** `multipart/form-data` with field `file`

**Response:**
```json
{
  "ingested_lines": 500,
  "chunks_stored": 87,
  "anomalies_found": 24,
  "time_ms": 3412
}
```

---

### `POST /ingest/text`
Ingest raw log text from the request body (useful for testing).

**Request:**
```json
{ "text": "192.168.1.1 - - [01/Jun/2024:10:00:00 +0000] \"GET /index.html HTTP/1.1\" 200 1234 \"-\" \"Mozilla/5.0\"" }
```

**Response:** Same as `/ingest`.

---

### `POST /query`
Query the log database in natural language using RAG.

**Request:**
```json
{
  "question": "Show me all failed login attempts",
  "filter_anomalies_only": false,
  "top_k": 5
}
```

**Response:**
```json
{
  "answer": "There were 3 failed login attempts from IP 192.168.1.10 at 10:01:00, 10:01:05, and 10:01:10 (HTTP 401).",
  "sources": ["192.168.1.10 POST /login -> 401 ...", "..."],
  "retrieval_ms": 42,
  "llm_ms": 1840
}
```

---

### `GET /anomalies`
Paginated list of anomalous log entries.

**Query parameters:**
| Param | Default | Description |
|-------|---------|-------------|
| `limit` | 50 | Results per page (max 200) |
| `offset` | 0 | Pagination offset |
| `min_score` | 0.0 | Minimum absolute anomaly score |

**Response:**
```json
{
  "items": [
    {
      "id": "uuid",
      "document": "1.2.3.4 POST /login?user=admin'-- ...",
      "is_anomaly": true,
      "anomaly_score": -0.872,
      "metadata": { "source_ip": "1.2.3.4", "status_code": 500 }
    }
  ],
  "total": 24,
  "offset": 0,
  "limit": 50
}
```

---

### `GET /anomalies/summary`
Aggregate statistics over all ingested logs.

**Response:**
```json
{
  "total_logs": 142,
  "total_anomalies": 24,
  "anomaly_rate": 16.9,
  "status_code_breakdown": { "500": 9, "403": 8, "400": 7 },
  "top_suspicious_ips": [
    { "ip": "1.2.3.4", "count": 12 }
  ]
}
```

---

## Configuration

All settings live in `.env` (copy from `.env.example`):

| Variable | Default | Description |
|----------|---------|-------------|
| `CHROMA_PERSIST_DIR` | `./data/chroma_db` | ChromaDB storage path |
| `CHROMA_COLLECTION_NAME` | `security_logs` | Collection name |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama API URL |
| `OLLAMA_MODEL` | `llama3.2` | LLM model name |
| `EMBEDDING_MODEL` | `all-MiniLM-L6-v2` | SentenceTransformer model |
| `LOG_LEVEL` | `INFO` | Logging verbosity |
| `API_HOST` | `0.0.0.0` | Bind address |
| `API_PORT` | `8000` | Bind port |
| `MAX_CHUNK_SIZE` | `500` | Max chars per log chunk |
| `CHUNK_OVERLAP` | `50` | Overlap chars between chunks |
| `RAG_TOP_K` | `5` | Context chunks retrieved per query |
| `ANOMALY_CONTAMINATION` | `0.05` | Expected anomaly fraction (0–0.5) |

---

## Running Tests

```bash
# Install dev dependencies
pip install -r requirements-dev.txt

# Run all tests with verbose output
pytest tests/ -v

# Run a specific test file
pytest tests/test_ingestion.py -v

# Run with coverage report
pytest tests/ --cov=app --cov-report=term-missing
```

---

## Docker Deployment

```bash
# Build and start all services
docker compose -f docker/docker-compose.yml up -d

# Pull the LLM model into Ollama
docker exec ai-security-ollama ollama pull llama3.2

# View API logs
docker logs ai-security-api -f

# Stop all services
docker compose -f docker/docker-compose.yml down
```

Or use the startup script (Linux/macOS):
```bash
chmod +x scripts/start.sh
./scripts/start.sh
```

---

## Project Structure

```
ai-security-log-analyst/
├── app/
│   ├── main.py                  # FastAPI app, startup, routing
│   ├── api/routes/
│   │   ├── ingest.py            # POST /ingest, POST /ingest/text
│   │   ├── query.py             # POST /query
│   │   └── anomaly.py           # GET /anomalies, GET /anomalies/summary
│   ├── core/
│   │   ├── config.py            # Pydantic-settings singleton
│   │   └── logger.py            # Loguru structured logging
│   ├── services/
│   │   ├── ingestion.py         # File loading + text chunking
│   │   ├── embedder.py          # SentenceTransformer wrapper
│   │   ├── vector_store.py      # ChromaDB CRUD
│   │   ├── rag_chain.py         # LangChain RAG pipeline
│   │   └── anomaly_detector.py  # Isolation Forest service
│   ├── models/
│   │   ├── log_entry.py         # LogEntry Pydantic model
│   │   └── query_models.py      # Request/Response schemas
│   └── utils/
│       └── log_parser.py        # Regex parsers (Apache/Syslog/KV)
├── data/
│   ├── raw_logs/                # Drop .log files here
│   ├── processed/               # Intermediate data
│   ├── chroma_db/               # ChromaDB persistent storage
│   └── models/                  # Saved Isolation Forest model
├── frontend/
│   ├── index.html               # Single-page dashboard
│   ├── style.css                # Dark-theme styles
│   └── app.js                   # Vanilla JS UI logic
├── tests/                       # pytest test suite
├── scripts/
│   ├── generate_sample_logs.py  # Synthetic log generator
│   ├── seed_vector_db.py        # One-shot DB seeding
│   ├── test_rag.py              # Manual RAG smoke test
│   └── start.sh                 # Docker bootstrap script
├── docker/
│   ├── Dockerfile
│   └── docker-compose.yml
├── .env.example
├── requirements.txt
├── requirements-dev.txt
└── README.md
```
