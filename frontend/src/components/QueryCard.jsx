import React, { useState, useCallback } from 'react';
import { queryLogs } from '../api.js';
import { useMouseGlow } from '../hooks/useMouseGlow.js';

const EXAMPLE_QUESTIONS = [
  'What are the most common error types?',
  'Are there any signs of brute-force attacks?',
  'Summarise suspicious activity in the last hour.',
  'Which IPs appear most frequently?',
];

export default function QueryCard({ onError, onSuccess }) {
  const [question, setQuestion] = useState('');
  const [loading, setLoading] = useState(false);
  const [answer, setAnswer] = useState(null);
  const [sources, setSources] = useState([]);
  const handleGlow = useMouseGlow();

  const submit = useCallback(async () => {
    const q = question.trim();
    if (!q || loading) return;
    setLoading(true);
    setAnswer(null);
    setSources([]);
    try {
      const result = await queryLogs(q);
      setAnswer(result.answer ?? result.response ?? JSON.stringify(result));
      setSources(result.sources ?? result.context ?? []);
      onSuccess?.();
    } catch (err) {
      onError(err.message || 'Query failed');
    } finally {
      setLoading(false);
    }
  }, [question, loading, onError, onSuccess]);

  const handleKey = (e) => {
    if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) submit();
  };

  return (
    <div className="card" onMouseMove={handleGlow}>
      <div className="card-header">
        <h2 className="card-title">
          <svg viewBox="0 0 20 20" fill="none" className="card-title-icon" aria-hidden="true">
            <circle cx="9" cy="9" r="5" stroke="currentColor" strokeWidth="1.5" />
            <path
              d="M15 15l-3-3"
              stroke="currentColor"
              strokeWidth="1.5"
              strokeLinecap="round"
            />
          </svg>
          Query Logs
        </h2>
      </div>

      <div className="card-body">
        {/* Example chips */}
        <div className="example-chips">
          {EXAMPLE_QUESTIONS.map((q) => (
            <button
              key={q}
              className="chip"
              type="button"
              onClick={() => setQuestion(q)}
            >
              {q}
            </button>
          ))}
        </div>

        <div className="input-row">
          <input
            className="query-input"
            type="text"
            placeholder="Ask a question about your logs… (Ctrl+Enter to submit)"
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            onKeyDown={handleKey}
            aria-label="Security query"
          />
          <button
            className="btn btn-primary"
            onClick={submit}
            disabled={loading || !question.trim()}
            type="button"
          >
            {loading ? <span className="spinner" aria-hidden="true" /> : 'Ask'}
          </button>
        </div>

        {/* Answer panel */}
        {(loading || answer) && (
          <div className="answer-panel" aria-live="polite">
            {loading ? (
              <div className="answer-loading">
                <span className="spinner spinner--lg" aria-hidden="true" />
                <span>Thinking…</span>
              </div>
            ) : (
              <>
                <p className="answer-text">{answer}</p>
                {sources.length > 0 && (
                  <details className="sources-details">
                    <summary className="sources-summary">
                      {sources.length} source{sources.length !== 1 ? 's' : ''} used
                    </summary>
                    <ul className="sources-list">
                      {sources.map((src, i) => (
                        <li key={i} className="sources-item">
                          {typeof src === 'string' ? src : JSON.stringify(src)}
                        </li>
                      ))}
                    </ul>
                  </details>
                )}
              </>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
