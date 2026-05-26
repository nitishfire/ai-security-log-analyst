import React, { useState, useCallback, useRef } from 'react';
import { queryLogs } from '../api.js';

const MAX_QUESTION_LEN = 2000; // mirrors backend QueryRequest.question max_length

const EXAMPLE_QUESTIONS = [
  'What are the most common error types?',
  'Are there any signs of brute-force attacks?',
  'Which IPs appear most frequently?',
  'Summarise suspicious activity.',
];

function renderSourceMeta(src) {
  if (typeof src === 'string') return src;
  const bits = [];
  if (src.chunk_index != null) bits.push(`chunk ${src.chunk_index}`);
  if (src.source_ip) bits.push(`ip ${src.source_ip}`);
  if (src.status_code) bits.push(`status ${src.status_code}`);
  if (src.path) bits.push(src.path);
  return bits.join(' · ');
}

function renderSourcePreview(src) {
  if (typeof src === 'string') return src;
  return src.preview || src.document || JSON.stringify(src);
}

export default function QueryCard({ onError }) {
  const [question, setQuestion] = useState('');
  const [filterAnomaliesOnly, setFilterAnomaliesOnly] = useState(false);
  const [topK, setTopK] = useState(5);
  const [loading, setLoading] = useState(false);
  const [answer, setAnswer] = useState(null);
  const [sources, setSources] = useState([]);
  const [elapsed, setElapsed] = useState(null);
  const textareaRef = useRef(null);

  const submit = useCallback(async () => {
    const q = question.trim();
    if (!q || loading) return;
    setLoading(true);
    setAnswer(null);
    setSources([]);
    setElapsed(null);
    const t0 = performance.now();
    try {
      const result = await queryLogs(q, { filterAnomaliesOnly, topK });
      setAnswer(result.answer ?? result.response ?? JSON.stringify(result));
      setSources(result.sources ?? result.context ?? []);
      setElapsed(((performance.now() - t0) / 1000).toFixed(2));
    } catch (err) {
      onError(err.message || 'Query failed');
    } finally {
      setLoading(false);
    }
  }, [question, loading, filterAnomaliesOnly, topK, onError]);

  const handleKey = (e) => {
    if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) submit();
  };

  const clearAll = () => {
    setQuestion('');
    setAnswer(null);
    setSources([]);
    setElapsed(null);
  };

  return (
    <section className="block" id="ask">
      {/* ── Block header ────────────────────────────────────────── */}
      <div className="block__head">
        <span className="block__num">02</span>
        <h2 className="block__title">Ask</h2>
      </div>

      {/* ── Example chips ────────────────────────────────────────── */}
      <div className="ask__chips">
        {EXAMPLE_QUESTIONS.map((q) => (
          <button
            key={q}
            className="chip"
            type="button"
            onClick={() => {
              setQuestion(q);
              textareaRef.current?.focus();
            }}
          >
            {q}
          </button>
        ))}
      </div>

      {/* ── Ask panel ────────────────────────────────────────────── */}
      <div className="ask">
        {/* Input + send button */}
        <div className="ask__input-wrap">
          <textarea
            ref={textareaRef}
            rows={3}
            placeholder="Ask a question about your logs… (Ctrl+Enter to submit)"
            value={question}
            onChange={(e) => setQuestion(e.target.value.slice(0, MAX_QUESTION_LEN))}
            onKeyDown={handleKey}
            aria-label="Security query"
            spellCheck={false}
            maxLength={MAX_QUESTION_LEN}
          />
          {question.length > MAX_QUESTION_LEN * 0.9 && (
            <span
              style={{
                position: 'absolute',
                bottom: '66px',
                right: '72px',
                fontSize: '.68rem',
                fontFamily: 'var(--mono)',
                color: question.length >= MAX_QUESTION_LEN ? 'var(--danger)' : 'var(--muted)',
              }}
              aria-live="polite"
            >
              {question.length}/{MAX_QUESTION_LEN}
            </span>
          )}
          <button
            className="btn-glyph"
            onClick={submit}
            disabled={loading || !question.trim()}
            type="button"
            aria-label="Submit query"
          >
            {loading ? (
              <span className="spinner" aria-hidden="true" />
            ) : (
              <svg viewBox="0 0 16 16" fill="none" width="16" height="16" aria-hidden="true">
                <path
                  d="M8 2v12M3 7l5-5 5 5"
                  stroke="currentColor"
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              </svg>
            )}
          </button>
        </div>

        {/* Controls */}
        <div className="ask__controls">
          {/* Anomalies-only toggle — uses hidden checkbox so CSS :checked works */}
          <label className="toggle-row">
            <span>Anomalies only</span>
            <input
              type="checkbox"
              checked={filterAnomaliesOnly}
              onChange={(e) => setFilterAnomaliesOnly(e.target.checked)}
              aria-label="Filter to anomalies only"
            />
            <span className="toggle-track" />
          </label>

          {/* Top-K picker */}
          <div className="ask__k">
            <label htmlFor="ask-topk">Top K</label>
            <input
              id="ask-topk"
              type="number"
              min={1}
              max={20}
              step={1}
              value={topK}
              onChange={(e) =>
                setTopK(Math.max(1, Math.min(20, Number(e.target.value) || 5)))
              }
              aria-label="Number of sources to retrieve"
            />
          </div>

          {(answer || question) && (
            <button className="btn btn-ghost btn-sm" type="button" onClick={clearAll}>
              Clear
            </button>
          )}
        </div>
      </div>

      {/* ── Answer panel ─────────────────────────────────────────── */}
      <div className={`ask__answer${answer || loading ? ' open' : ''}`} aria-live="polite">
        {loading && (
          <div className="answer-loading">
            <span className="spinner" aria-hidden="true" />
            <span>Thinking…</span>
          </div>
        )}

        {answer && !loading && (
          <div className="answer-box">
            <p className="answer-text">{answer}</p>

            <div className="ask__answer-foot">
              {elapsed && (
                <span className="timing">
                  {elapsed}s &mdash; {sources.length} source{sources.length !== 1 ? 's' : ''}
                </span>
              )}

              {sources.length > 0 && (
                <details className="sources">
                  <summary>
                    {sources.length} source{sources.length !== 1 ? 's' : ''} used
                  </summary>
                  <ul style={{ listStyle: 'none', marginTop: '10px', display: 'flex', flexDirection: 'column', gap: '8px' }}>
                    {sources.map((src, i) => (
                      <li key={i}>
                        {renderSourceMeta(src) && (
                          <div style={{ fontFamily: 'var(--mono)', fontSize: '.7rem', color: 'var(--muted)', marginBottom: '4px' }}>
                            {renderSourceMeta(src)}
                          </div>
                        )}
                        <pre className="source-chunk">{renderSourcePreview(src)}</pre>
                      </li>
                    ))}
                  </ul>
                </details>
              )}
            </div>
          </div>
        )}
      </div>
    </section>
  );
}
