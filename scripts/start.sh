#!/usr/bin/env bash
# ============================================================
# start.sh  —  Bootstrap the AI Security Log Analyst stack
# ============================================================
set -euo pipefail

OLLAMA_URL="http://localhost:11434"
API_URL="http://localhost:8000"
COMPOSE_FILE="docker/docker-compose.yml"
MODEL="llama3.2"

echo "============================================"
echo "  AI Security Log Analyst — Startup Script"
echo "============================================"

# ── 1. Launch containers ────────────────────────────────────────
echo "[1/4] Starting Docker Compose stack..."
docker compose -f "$COMPOSE_FILE" up -d
echo "      Containers started."

# ── 2. Wait for Ollama ──────────────────────────────────────────
echo "[2/4] Waiting for Ollama to be ready..."
max_attempts=30
attempt=0
until curl -sf "${OLLAMA_URL}/api/tags" > /dev/null 2>&1; do
  attempt=$((attempt + 1))
  if [[ $attempt -ge $max_attempts ]]; then
    echo "ERROR: Ollama did not become ready after ${max_attempts} attempts."
    echo "       Check: docker logs ai-security-ollama"
    exit 1
  fi
  echo "      Waiting... (attempt ${attempt}/${max_attempts})"
  sleep 5
done
echo "      Ollama is ready."

# ── 3. Pull the LLM model ───────────────────────────────────────
echo "[3/4] Pulling model '${MODEL}' into Ollama (may take a few minutes on first run)..."
docker exec ai-security-ollama ollama pull "${MODEL}"
echo "      Model '${MODEL}' ready."

# ── 4. Wait for API ─────────────────────────────────────────────
echo "[4/4] Waiting for API to be ready..."
attempt=0
until curl -sf "${API_URL}/health" > /dev/null 2>&1; do
  attempt=$((attempt + 1))
  if [[ $attempt -ge 20 ]]; then
    echo "ERROR: API did not become ready. Check: docker logs ai-security-api"
    exit 1
  fi
  echo "      Waiting... (attempt ${attempt}/20)"
  sleep 5
done

echo ""
echo "============================================"
echo "  System ready!"
echo "  Dashboard : ${API_URL}"
echo "  API docs  : ${API_URL}/docs"
echo "  Ollama    : ${OLLAMA_URL}"
echo "============================================"
