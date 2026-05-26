import React, { useState, useEffect, useCallback } from 'react';
import { fetchAnomalies } from '../api.js';

const PAGE_SIZE = 20;

/** Returns badge class based on anomaly score (negative = more anomalous). */
function scoreBadgeClass(score) {
  const s = parseFloat(score);
  if (!isFinite(s)) return 'badge badge-warning';
  // Scores below -0.5 are clearly anomalous → danger
  return s < -0.5 ? 'badge badge-danger' : 'badge badge-warning';
}

function clampScore(value) {
  const n = Number.parseFloat(value);
  return Number.isFinite(n) ? Math.min(1, Math.max(0, n)) : 0;
}

/** Truncate a string for display in table cell. */
function truncate(str, max = 120) {
  if (!str) return '—';
  return str.length > max ? str.slice(0, max) + '…' : str;
}

export default function AnomalyTable({ refreshKey }) {
  const [rows, setRows] = useState([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [minScore, setMinScore] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchAnomalies({
        limit: PAGE_SIZE,
        offset,
        min_score: minScore > 0 ? minScore : undefined,
      });
      // API returns AnomalyListResponse with `items` list
      setRows(data.items ?? data.anomalies ?? data.results ?? []);
      setTotal(data.total ?? 0);
    } catch (err) {
      setError(err.message || 'Could not load anomalies.');
    } finally {
      setLoading(false);
    }
  }, [offset, minScore, refreshKey]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    load();
  }, [load]);

  const totalPages = Math.ceil(total / PAGE_SIZE);
  const currentPage = Math.floor(offset / PAGE_SIZE) + 1;

  return (
    <section className="block" id="anomalies">
      {/* ── Block header ────────────────────────────────────────── */}
      <div className="block__head">
        <span className="block__num">03</span>
        <h2 className="block__title">Anomalous entries</h2>
        {total > 0 && (
          <span className="badge badge-violet">{total.toLocaleString()}</span>
        )}

        {/* Controls — margin-left: auto pushes to right */}
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
            onChange={(e) => {
              setMinScore(clampScore(e.target.value));
              setOffset(0);
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
              <span className="spinner" aria-hidden="true" />
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

      {/* ── Error state ──────────────────────────────────────────── */}
      {error && (
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            gap: '12px',
            padding: '16px 0',
            color: 'var(--danger)',
            fontSize: '.82rem',
            borderBottom: '1px solid var(--border)',
            marginBottom: '16px',
          }}
        >
          <span>⚠ {error}</span>
          <button className="btn btn-ghost btn-sm" onClick={load} type="button">
            Retry
          </button>
        </div>
      )}

      {/* ── Empty state ──────────────────────────────────────────── */}
      {!error && rows.length === 0 && !loading && (
        <div className="placeholder">
          <p>No anomalies detected yet.</p>
          <p style={{ marginTop: '6px', fontSize: '.8rem', color: 'var(--muted-2)' }}>
            Ingest some logs to get started.
          </p>
        </div>
      )}

      {/* ── Table ────────────────────────────────────────────────── */}
      {rows.length > 0 && (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Score</th>
                <th>IP</th>
                <th>Status</th>
                <th>Path</th>
                <th>Log excerpt</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((item, i) => {
                const score = item.anomaly_score ?? item.score ?? 0;
                const meta = item.metadata ?? {};
                const ip = meta.source_ip ?? meta.ip ?? '—';
                const status = meta.status_code ?? meta.status ?? '—';
                const path = meta.path ?? meta.url ?? '—';
                const excerpt =
                  item.document ?? item.raw ?? item.message ?? JSON.stringify(item);

                return (
                  <tr
                    key={item.id ?? i}
                    style={{ animation: `row-in 300ms var(--ease-out) ${i * 25}ms both` }}
                  >
                    <td>
                      <span className={scoreBadgeClass(score)}>
                        {isFinite(parseFloat(score))
                          ? parseFloat(score).toFixed(3)
                          : '—'}
                      </span>
                    </td>
                    <td
                      style={{ fontFamily: 'var(--mono)', fontSize: '.76rem', color: 'var(--text-dim)' }}
                    >
                      {ip}
                    </td>
                    <td
                      style={{ fontFamily: 'var(--mono)', fontSize: '.76rem', color: 'var(--text-dim)' }}
                    >
                      {status}
                    </td>
                    <td
                      title={path}
                      style={{
                        maxWidth: '200px',
                        overflow: 'hidden',
                        textOverflow: 'ellipsis',
                        whiteSpace: 'nowrap',
                        fontFamily: 'var(--mono)',
                        fontSize: '.74rem',
                        color: 'var(--muted)',
                      }}
                    >
                      {path}
                    </td>
                    <td title={excerpt} style={{ maxWidth: '400px' }}>
                      {truncate(excerpt)}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {/* ── Pagination ───────────────────────────────────────────── */}
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
    </section>
  );
}
