import React, { useState, useEffect, useCallback } from 'react';
import { fetchAnomalies } from '../api.js';
import { useMouseGlow } from '../hooks/useMouseGlow.js';

const PAGE_SIZE = 20;

function scoreClass(score) {
  const abs = Math.abs(score);
  if (abs >= 0.7) return 'severity-high';
  if (abs >= 0.4) return 'severity-medium';
  return 'severity-low';
}

function scoreLabel(score) {
  const abs = Math.abs(score);
  if (abs >= 0.7) return 'High';
  if (abs >= 0.4) return 'Medium';
  return 'Low';
}

function formatTs(ts) {
  if (!ts) return '—';
  try {
    return new Date(ts).toLocaleString(undefined, {
      dateStyle: 'short',
      timeStyle: 'medium',
    });
  } catch (_) {
    return ts;
  }
}

function getErrorMessage(err) {
  if (!err) return 'Could not load anomalies.';
  if (typeof err === 'string') return err;

  const message = err.message || String(err);
  try {
    const parsed = JSON.parse(message);
    if (Array.isArray(parsed.detail)) {
      return parsed.detail.map((item) => item.msg || JSON.stringify(item)).join(' ');
    }
    if (parsed.detail) return String(parsed.detail);
  } catch (_) {
    // Not a JSON API error; use the original message.
  }

  return message;
}

function clampScore(value) {
  const score = Number.parseFloat(value);
  if (!Number.isFinite(score)) return 0;
  return Math.min(1, Math.max(0, score));
}

export default function AnomalyTable({ refreshKey }) {
  const [rows, setRows] = useState([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [minScore, setMinScore] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const handleGlow = useMouseGlow();

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchAnomalies({
        limit: PAGE_SIZE,
        offset,
        min_score: minScore > 0 ? minScore : undefined,
      });
      const items = data.items ?? data.anomalies ?? data.results ?? [];
      setRows(items);
      setTotal(data.total ?? items.length);
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setLoading(false);
    }
  }, [offset, minScore, refreshKey]);

  useEffect(() => {
    load();
  }, [load]);

  // Reset to page 0 when filter changes
  const handleScoreChange = (e) => {
    setMinScore(clampScore(e.target.value));
    setOffset(0);
  };

  const totalPages = Math.ceil(total / PAGE_SIZE);
  const currentPage = Math.floor(offset / PAGE_SIZE) + 1;

  return (
    <div className="card card--wide" onMouseMove={handleGlow}>
      <div className="card-header">
        <h2 className="card-title">
          <svg viewBox="0 0 20 20" fill="none" className="card-title-icon" aria-hidden="true">
            <path
              d="M10 3L2 17h16L10 3Z"
              stroke="currentColor"
              strokeWidth="1.5"
              strokeLinejoin="round"
            />
            <path
              d="M10 9v4M10 15h.01"
              stroke="currentColor"
              strokeWidth="1.5"
              strokeLinecap="round"
            />
          </svg>
          Detected Anomalies
          {total > 0 && (
            <span className="card-badge">{total.toLocaleString()}</span>
          )}
        </h2>

        <div className="table-controls">
          <label className="filter-label" htmlFor="min-score">
            Min score
          </label>
          <input
            id="min-score"
            className="filter-input"
            type="number"
            min="0"
            max="1"
            step="0.05"
            value={minScore || ''}
            placeholder="0.0"
            onChange={handleScoreChange}
            onBlur={(e) => {
              e.target.value = minScore || '';
            }}
          />
          <button
            className="btn btn-ghost btn-sm"
            onClick={load}
            disabled={loading}
            type="button"
            aria-label="Refresh anomalies"
          >
            {loading ? (
              <span className="spinner spinner--sm" aria-hidden="true" />
            ) : (
              <svg viewBox="0 0 16 16" fill="none" width="14" height="14" aria-hidden="true">
                <path
                  d="M2 8a6 6 0 1 1 1.5 4"
                  stroke="currentColor"
                  strokeWidth="1.5"
                  strokeLinecap="round"
                />
                <path
                  d="M2 12V8h4"
                  stroke="currentColor"
                  strokeWidth="1.5"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              </svg>
            )}
          </button>
        </div>
      </div>

      <div className="card-body card-body--flush">
        {error && (
          <div className="table-error">
            <span>⚠ {error}</span>
            <button className="btn btn-ghost btn-sm" onClick={load} type="button">
              Retry
            </button>
          </div>
        )}

        {!error && rows.length === 0 && !loading && (
          <div className="table-empty">
            <svg viewBox="0 0 48 48" fill="none" className="empty-icon" aria-hidden="true">
              <path
                d="M24 6a18 18 0 1 0 0 36A18 18 0 0 0 24 6Z"
                stroke="currentColor"
                strokeWidth="1.5"
              />
              <path
                d="M24 16v8M24 28h.01"
                stroke="currentColor"
                strokeWidth="1.5"
                strokeLinecap="round"
              />
            </svg>
            <p>No anomalies detected yet.</p>
            <p className="table-empty-hint">Ingest some logs to get started.</p>
          </div>
        )}

        {rows.length > 0 && (
          <div className="table-scroll">
            <table className="anomaly-table">
              <thead>
                <tr>
                  <th>Timestamp</th>
                  <th>Severity</th>
                  <th>Score</th>
                  <th>Source</th>
                  <th>Message</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row, i) => {
                  const score = row.anomaly_score ?? row.score ?? 0;
                  const meta = row.metadata ?? {};
                  const timestamp = row.timestamp ?? meta.timestamp ?? meta.timestamp_raw;
                  const source = row.source ?? row.filename ?? meta.source_ip ?? '—';
                  const message = row.message ?? row.raw ?? row.document ?? '';
                  return (
                    <tr key={row.id ?? i} className="table-row">
                      <td className="td-ts">{formatTs(timestamp)}</td>
                      <td>
                        <span className={`severity-badge ${scoreClass(score)}`}>
                          {scoreLabel(score)}
                        </span>
                      </td>
                      <td className="td-score">{Number(score).toFixed(3)}</td>
                      <td className="td-source">{source}</td>
                      <td className="td-message" title={message || JSON.stringify(row)}>
                        {message || JSON.stringify(row)}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}

        {/* Pagination */}
        {totalPages > 1 && (
          <div className="pagination">
            <button
              className="btn btn-ghost btn-sm"
              disabled={offset === 0}
              onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
              type="button"
            >
              ← Prev
            </button>
            <span className="pagination-info">
              Page {currentPage} of {totalPages}
            </span>
            <button
              className="btn btn-ghost btn-sm"
              disabled={offset + PAGE_SIZE >= total}
              onClick={() => setOffset(offset + PAGE_SIZE)}
              type="button"
            >
              Next →
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
