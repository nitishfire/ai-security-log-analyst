// ── API helpers ──────────────────────────────────────────────────────────────
// All endpoints are relative so Vite proxy (dev) or same-origin (prod) handles
// routing to the FastAPI backend at :8000.

const BASE = '';

async function handleResponse(res) {
  if (!res.ok) {
    let msg = `HTTP ${res.status}`;
    try {
      const body = await res.json();
      msg = body.detail || body.message || JSON.stringify(body);
    } catch (_) {
      // ignore parse errors
    }
    throw new Error(msg);
  }
  return res.json();
}

/** GET /health */
export async function fetchHealth() {
  const res = await fetch(`${BASE}/health`);
  return handleResponse(res);
}

/** GET /anomalies/summary */
export async function fetchAnomalySummary({ uploadId = null } = {}) {
  const qs = new URLSearchParams();
  if (uploadId) qs.set('upload_id', uploadId);
  const suffix = qs.toString() ? `?${qs}` : '';
  const res = await fetch(`${BASE}/anomalies/summary${suffix}`);
  return handleResponse(res);
}

/**
 * POST /ingest — upload a log file
 * @param {File} file
 */
export async function ingestFile(file) {
  const form = new FormData();
  form.append('file', file);
  const res = await fetch(`${BASE}/ingest`, {
    method: 'POST',
    body: form,
  });
  return handleResponse(res);
}

/**
 * POST /ingest/text — ingest raw log text
 * @param {string} text
 */
export async function ingestText(text) {
  const res = await fetch(`${BASE}/ingest/text`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text }),
  });
  return handleResponse(res);
}

/**
 * POST /query — ask the RAG chain a question
 * @param {string} question
 * @param {{ filterAnomaliesOnly?: boolean, topK?: number, uploadId?: string }} opts
 */
export async function queryLogs(
  question,
  { filterAnomaliesOnly = false, topK = 5, uploadId = null } = {}
) {
  const body = {
    question,
    filter_anomalies_only: filterAnomaliesOnly,
    top_k: topK,
  };
  if (uploadId) body.upload_id = uploadId;

  const res = await fetch(`${BASE}/query`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  return handleResponse(res);
}

/**
 * GET /anomalies — list detected anomalies
 * @param {{ limit?: number, offset?: number, min_score?: number, uploadId?: string }} params
 */
export async function fetchAnomalies(params = {}) {
  const qs = new URLSearchParams();
  if (params.limit != null) qs.set('limit', params.limit);
  if (params.offset != null) qs.set('offset', params.offset);
  if (params.min_score != null) qs.set('min_score', params.min_score);
  if (params.uploadId) qs.set('upload_id', params.uploadId);
  const res = await fetch(`${BASE}/anomalies?${qs}`);
  return handleResponse(res);
}
