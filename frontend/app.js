/**
 * AI Security Log Analyst — Dashboard JS
 * Vanilla JS, no dependencies.
 */

'use strict';

const API = '';   // same origin; change to 'http://localhost:8000' if serving separately

// ── Utility ─────────────────────────────────────────────────────────────────

function toast(msg, type = 'info', duration = 4000) {
  const el = document.createElement('div');
  el.className = `toast ${type}`;
  el.textContent = msg;
  document.getElementById('toast-container').appendChild(el);
  setTimeout(() => el.remove(), duration);
}

function setSpinner(id, show) {
  const el = document.getElementById(id);
  if (el) el.style.display = show ? 'inline-block' : 'none';
}

async function apiFetch(path, opts = {}) {
  const res = await fetch(API + path, opts);
  if (!res.ok) {
    let detail = res.statusText;
    try { const j = await res.json(); detail = j.detail || JSON.stringify(j); } catch {}
    throw new Error(detail);
  }
  return res.json();
}

// ── Health polling ───────────────────────────────────────────────────────────

async function checkHealth() {
  const dot  = document.getElementById('status-dot');
  const text = document.getElementById('status-text');
  try {
    const data = await apiFetch('/health');
    dot.className  = 'status-dot online';
    text.textContent = 'API online';
    document.getElementById('stat-model').textContent     = data.model     || '—';
    document.getElementById('stat-embedding').textContent = data.embedding_model || '—';
    document.getElementById('stat-total').textContent     = data.chroma_docs ?? '—';
  } catch {
    dot.className  = 'status-dot offline';
    text.textContent = 'API offline';
  }
}

async function refreshStats() {
  try {
    const data = await apiFetch('/anomalies/summary');
    document.getElementById('stat-total').textContent     = data.total_logs ?? '—';
    document.getElementById('stat-anomalies').textContent = data.total_anomalies ?? '—';
    document.getElementById('stat-rate').textContent      = data.anomaly_rate != null
      ? data.anomaly_rate.toFixed(1) + '%' : '—';
  } catch { /* silently ignore if no data yet */ }
}

// Poll every 10 seconds
checkHealth();
refreshStats();
setInterval(() => { checkHealth(); refreshStats(); }, 10_000);

// ── Upload ───────────────────────────────────────────────────────────────────

const dropZone  = document.getElementById('drop-zone');
const fileInput = document.getElementById('file-input');
const btnUpload = document.getElementById('btn-upload');
let selectedFile = null;

dropZone.addEventListener('click', () => fileInput.click());

dropZone.addEventListener('dragover', e => {
  e.preventDefault();
  dropZone.classList.add('drag-over');
});
dropZone.addEventListener('dragleave', () => dropZone.classList.remove('drag-over'));
dropZone.addEventListener('drop', e => {
  e.preventDefault();
  dropZone.classList.remove('drag-over');
  const f = e.dataTransfer.files[0];
  if (f) setFile(f);
});

fileInput.addEventListener('change', () => {
  if (fileInput.files[0]) setFile(fileInput.files[0]);
});

function setFile(f) {
  if (!f.name.match(/\.(log|txt)$/i)) {
    toast('Only .log and .txt files are accepted.', 'error');
    return;
  }
  selectedFile = f;
  document.getElementById('drop-filename').textContent = f.name + ' (' + (f.size/1024).toFixed(1) + ' KB)';
  btnUpload.disabled = false;
}

document.getElementById('btn-clear-upload').addEventListener('click', () => {
  selectedFile = null;
  fileInput.value = '';
  document.getElementById('drop-filename').textContent = '';
  btnUpload.disabled = true;
  document.getElementById('ingest-result').style.display = 'none';
});

btnUpload.addEventListener('click', async () => {
  if (!selectedFile) return;
  btnUpload.disabled = true;
  setSpinner('upload-spinner', true);
  try {
    const form = new FormData();
    form.append('file', selectedFile);
    const data = await apiFetch('/ingest', { method: 'POST', body: form });
    renderIngestResult(data);
    toast(`Ingested ${data.ingested_lines} lines, ${data.anomalies_found} anomalies found.`, 'success');
    refreshStats();
    loadAnomalies();
  } catch (err) {
    toast('Ingest failed: ' + err.message, 'error');
  } finally {
    btnUpload.disabled = false;
    setSpinner('upload-spinner', false);
  }
});

function renderIngestResult(data) {
  const el = document.getElementById('ingest-result');
  el.style.display = 'block';
  el.innerHTML = `
    <div class="ingest-result">
      <div class="ingest-result-item">
        <div class="num">${data.ingested_lines}</div>
        <div class="lbl">Lines Parsed</div>
      </div>
      <div class="ingest-result-item">
        <div class="num">${data.chunks_stored}</div>
        <div class="lbl">Chunks Stored</div>
      </div>
      <div class="ingest-result-item">
        <div class="num" style="color:var(--danger)">${data.anomalies_found}</div>
        <div class="lbl">Anomalies</div>
      </div>
      <div class="ingest-result-item">
        <div class="num" style="font-size:1rem">${data.time_ms} ms</div>
        <div class="lbl">Total Time</div>
      </div>
    </div>`;
}

// ── Query ─────────────────────────────────────────────────────────────────────

document.getElementById('btn-query').addEventListener('click', runQuery);
document.getElementById('query-input').addEventListener('keydown', e => {
  if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) runQuery();
});

document.getElementById('btn-clear-query').addEventListener('click', () => {
  document.getElementById('query-input').value = '';
  document.getElementById('answer-container').style.display = 'none';
});

async function runQuery() {
  const question = document.getElementById('query-input').value.trim();
  if (!question) { toast('Please enter a question.', 'info'); return; }

  const btn = document.getElementById('btn-query');
  btn.disabled = true;
  setSpinner('query-spinner', true);

  try {
    const body = {
      question,
      filter_anomalies_only: document.getElementById('anomaly-only').checked,
      top_k: parseInt(document.getElementById('top-k').value, 10) || 5,
    };
    const data = await apiFetch('/query', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    renderAnswer(data);
  } catch (err) {
    toast('Query failed: ' + err.message, 'error');
  } finally {
    btn.disabled = false;
    setSpinner('query-spinner', false);
  }
}

function renderAnswer(data) {
  const container = document.getElementById('answer-container');
  container.style.display = 'block';

  document.getElementById('answer-box').textContent = data.answer || '(No answer)';
  document.getElementById('query-timing').textContent =
    `Retrieval: ${data.retrieval_ms}ms  |  LLM: ${data.llm_ms}ms`;

  const sourcesList = document.getElementById('sources-list');
  sourcesList.innerHTML = '';
  (data.sources || []).forEach((chunk, i) => {
    const div = document.createElement('div');
    div.className = 'source-chunk';
    div.textContent = `[${i + 1}] ${chunk}`;
    sourcesList.appendChild(div);
  });

  const details = document.getElementById('sources-details');
  details.querySelector('summary').textContent =
    `View ${(data.sources || []).length} source chunks`;
}

// ── Anomaly table ────────────────────────────────────────────────────────────

document.getElementById('btn-refresh-anomalies').addEventListener('click', loadAnomalies);

async function loadAnomalies() {
  const tbody = document.getElementById('anomaly-tbody');
  setSpinner('anom-spinner', true);
  try {
    const data = await apiFetch('/anomalies?limit=100');
    if (!data.items || data.items.length === 0) {
      tbody.innerHTML = '<tr><td colspan="5" class="placeholder">No anomalies detected yet</td></tr>';
      return;
    }
    tbody.innerHTML = data.items.map(item => {
      const meta = item.metadata || {};
      const score = parseFloat(item.anomaly_score || 0).toFixed(3);
      const scoreBadge = parseFloat(score) < -0.5
        ? `<span class="badge badge-danger">${score}</span>`
        : `<span class="badge badge-warning">${score}</span>`;
      const ip   = meta.source_ip  || '—';
      const sc   = meta.status_code || '—';
      const path = (meta.path || '').substring(0, 40) || '—';
      const doc  = (item.document || '').substring(0, 120).replace(/</g,'&lt;');
      return `<tr>
        <td>${scoreBadge}</td>
        <td style="font-family:var(--mono)">${ip}</td>
        <td>${renderStatusBadge(sc)}</td>
        <td style="font-family:var(--mono);font-size:.75rem" title="${path}">${path}</td>
        <td style="font-family:var(--mono);font-size:.72rem;color:var(--muted)">${doc}</td>
      </tr>`;
    }).join('');
  } catch (err) {
    tbody.innerHTML = `<tr><td colspan="5" class="placeholder" style="color:var(--danger)">Error: ${err.message}</td></tr>`;
  } finally {
    setSpinner('anom-spinner', false);
  }
}

function renderStatusBadge(code) {
  const n = parseInt(code, 10);
  if (n >= 500) return `<span class="badge badge-danger">${code}</span>`;
  if (n >= 400) return `<span class="badge badge-warning">${code}</span>`;
  return `<span class="badge badge-ok">${code}</span>`;
}

// Load anomalies on page load
loadAnomalies();
