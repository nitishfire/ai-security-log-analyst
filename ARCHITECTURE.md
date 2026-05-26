# Architecture Decision Record — AI Security Log Analyst

**Author:** Nitish Shankar Mudaliar (A00336067)  
**Supervisor:** Peter Vargovcik  
**Date:** May 2026

---

## 1. Why RAG Over Fine-Tuning for This Use Case

### The Problem
Security logs are inherently dynamic. New log sources, new attack patterns, and new infrastructure are introduced continuously. A model fine-tuned on last month's logs would rapidly go stale and require expensive retraining cycles.

### RAG as the Solution
Retrieval-Augmented Generation separates *knowledge* (the logs) from *reasoning* (the LLM). The LLM is never retrained; only the vector store is updated when new logs are ingested. This gives us:

| Concern | Fine-Tuning | RAG |
|---------|-------------|-----|
| Knowledge freshness | Retrain every update | Re-ingest in seconds |
| Cost | GPU hours per update | Near-zero per update |
| Explainability | Black-box weights | Traceable source chunks |
| Data privacy | Logs leave the system | Fully local |
| Hallucination control | Hard to constrain | Prompt forces context-only answers |

The system prompt enforces: *"Use ONLY the following log excerpts to answer. If not in the logs, say 'Not found in logs.'"* This makes the LLM a reasoning layer over retrieved evidence rather than a memorised knowledge store — critical for security forensics where fabricated answers could be dangerous.

---

## 2. Embedding Model Selection: `all-MiniLM-L6-v2`

### Candidates Considered

| Model | Dims | Size | Speed | Quality |
|-------|------|------|-------|---------|
| `all-MiniLM-L6-v2` | 384 | 22 MB | ★★★★★ | ★★★★☆ |
| `all-mpnet-base-v2` | 768 | 420 MB | ★★★☆☆ | ★★★★★ |
| `paraphrase-MiniLM-L3-v2` | 384 | 17 MB | ★★★★★ | ★★★☆☆ |
| OpenAI `text-embedding-3-small` | 1536 | Cloud | ★★★★☆ | ★★★★★ |

### Why `all-MiniLM-L6-v2`

1. **Speed**: 6-layer MiniLM encodes ~14,000 sentences/second on CPU. Security log batches of hundreds or thousands of lines process in under a second.
2. **Size**: At 22 MB it fits comfortably in memory and loads in ~200 ms on first call.
3. **Quality**: SBERT benchmarks show 78.9 Spearman correlation on STS tasks — sufficient for log retrieval where the vocabulary is highly structured (IP addresses, HTTP methods, status codes, paths) rather than nuanced natural language.
4. **Privacy**: Entirely local — no log data ever leaves the machine, critical for security applications.
5. **384 dimensions**: Compact enough for ChromaDB to store thousands of documents without memory pressure, yet rich enough for meaningful cosine similarity over log content.

`all-mpnet-base-v2` would yield marginally better semantic quality but at ~20× the model size and 4× slower encoding — not justified for structured log text.

---

## 3. Vector Database: ChromaDB vs FAISS vs Pinecone

### Candidates Considered

| Factor | ChromaDB | FAISS | Pinecone |
|--------|----------|-------|----------|
| Deployment | Local process | Local library | Cloud SaaS |
| API key required | No | No | Yes |
| Persistent storage | Yes (SQLite + files) | Manual (pickle) | Managed |
| Metadata filtering | Built-in | Not built-in | Built-in |
| Python API | High-level | Low-level | High-level |
| Cost | Free | Free | Paid tiers |
| Setup complexity | `pip install` | `pip install` | Sign-up + billing |

### Why ChromaDB

1. **Zero-config persistence**: ChromaDB uses a local SQLite-backed store. The entire vector index survives process restarts with a single `path=` argument — no manual serialisation required.
2. **Metadata filtering**: The `where={"is_anomaly": True}` filter is a first-class ChromaDB feature. FAISS would require a custom post-filter step over returned indices.
3. **No external dependencies**: The project requirement was a fully self-contained, offline-capable system. Pinecone's cloud dependency violates privacy requirements for security data.
4. **Developer ergonomics**: `collection.add()`, `collection.query()`, `collection.get()` cover all needs with minimal boilerplate compared to FAISS's index management.
5. **Cosine similarity**: Native `hnsw:space=cosine` metadata on collection creation gives semantically correct similarity for normalised SentenceTransformer vectors.

**Trade-off acknowledged**: ChromaDB is not optimised for billion-scale vectors. For production at scale, migration to Qdrant or Milvus (both support local deployment with metadata filtering) would be appropriate.

---

## 4. Isolation Forest Rationale

### Why Unsupervised

Security log anomaly detection faces a classic labelled-data problem: *we don't know what we haven't seen yet*. Novel attack patterns by definition do not appear in historical labelled datasets. Supervised approaches (SVM, neural classifiers) optimise for known attack signatures and systematically miss zero-day exploits.

Isolation Forest is an ensemble of random decision trees that isolates points by partitioning the feature space. Anomalous points require fewer splits to isolate because they are sparse and different — this is the "isolation" principle. Key properties for this use case:

1. **Unsupervised**: Requires no labelled training data. Fits on any batch of logs.
2. **Fast inference**: O(n log n) fit, O(n) predict — handles thousands of entries in milliseconds.
3. **Contamination parameter**: `contamination=0.05` sets the expected anomaly fraction, calibrated to the known distribution of security log datasets (~5% suspicious traffic in typical enterprise environments).
4. **Interpretable features**: Unlike neural anomaly detectors, the 9-feature vector (status code, bytes sent, path depth, suspicious keywords, hour of day, request rate) is human-interpretable. A security analyst can understand *why* a record was flagged.
5. **Persisted model**: The fitted `IsolationForest` is serialised to `data/models/isolation_forest.pkl`. Subsequent ingestions reuse the same model, maintaining consistency across sessions.

### Feature Engineering Rationale

| Feature | Rationale |
|---------|-----------|
| `status_code` | 4xx/5xx codes are primary indicators of attacks or misconfigurations |
| `bytes_sent` | Exfiltration produces abnormally large responses; scanners produce 0-byte responses |
| `bytes_log` | Log-scale normalisation reduces outlier dominance while preserving information |
| `is_post` | POST-heavy traffic to non-API paths is characteristic of brute-force and injection |
| `is_error` | Direct measure of failed requests |
| `path_depth` | Path traversal attacks (`../../etc/passwd`) produce high depth values |
| `has_suspicious_path` | Keyword match on known attack targets (admin, wp-login, .env, etc.) |
| `hour_of_day` | Automated attacks often occur at unusual hours; cyclical encoding could improve this |
| `request_rate_1min` | Per-IP frequency identifies scanning/brute-force from a single source |

---

## 5. LangChain Chain Design Decisions

### Version: LangChain v0.2

LangChain 0.2 introduced the LCEL (LangChain Expression Language) `|` pipe operator for composing chains. This project uses it in `build_rag_chain()` for advanced usage while keeping the `query()` function as a simpler, more testable implementation.

### Retriever Design

Rather than using LangChain's built-in `Chroma` retriever class, the project wraps `vector_store.similarity_search()` directly. This gives:
- **Full control over `where` metadata filters** (required for `filter_anomalies_only` mode)
- **Timing instrumentation** at the retrieval boundary
- **Cleaner separation of concerns** — the vector store service is independently testable

### Prompt Engineering

The system prompt was designed with two hard constraints:

1. **Context-only policy**: *"Use ONLY the following log excerpts"* — prevents the LLM from hallucinating log events that aren't in the retrieved context
2. **Explicit fallback phrase**: *"If the answer is not in the logs, say 'Not found in logs.'"* — gives the LLM a safe exit that signals to the caller whether the answer was grounded

`temperature=0.1` suppresses creative variation in favour of factual consistency — appropriate for forensic analysis.

### Graceful Degradation

The Ollama server is checked with a 3-second HTTP probe before every LLM call. If Ollama is unavailable:
- Retrieved context chunks are still returned to the caller
- A clear error message is returned rather than an exception
- The API continues serving ingest and anomaly endpoints without interruption

This is important in containerised deployments where the Ollama service may be starting up or restarting independently of the API service.

---

## 6. Key Design Patterns

### Singleton Services
`embedder.py`, `vector_store.py`, and `anomaly_detector.py` all use module-level singletons with lazy initialisation. The first call loads the model/connection; subsequent calls reuse it. This avoids repeated expensive initialisation across API requests while keeping the code testable (singletons can be reset between tests).

### Pydantic Settings with `@lru_cache`
`config.py` uses `pydantic-settings` with `@lru_cache(maxsize=1)`. The `.env` file is read exactly once at startup. This is both a performance optimisation and a correctness guarantee — settings cannot drift mid-request.

### Loguru Structured Logging
Production deployments write JSON-serialised log lines to both stdout (for container log aggregators like CloudWatch or Loki) and a rotating file. Development mode uses colourised human-readable output. The `get_logger(name)` factory binds the module name to every log record, enabling source-level filtering in log management platforms.

### Overlap-Based Chunking
Log chunks use a character-level sliding window with configurable overlap (default 50 chars). This ensures that log entries at chunk boundaries appear in at least two adjacent chunks, so a query that spans multiple lines (e.g. a brute-force sequence) retrieves the full context window rather than a truncated view.
