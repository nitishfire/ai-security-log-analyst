import React, { useEffect, useRef, useState } from 'react';

/** Animates a number from 0 to `target` over `duration` ms (ease-out cubic). */
function useCountUp(target, duration = 900) {
  const [value, setValue] = useState(0);
  const rafRef = useRef(null);
  const prevRef = useRef(0);

  useEffect(() => {
    const end = Number(target) || 0;
    const start = prevRef.current;
    if (start === end) return;
    const t0 = performance.now();
    const tick = (now) => {
      const p = Math.min((now - t0) / duration, 1);
      const eased = 1 - Math.pow(1 - p, 3);
      setValue(Math.round(start + eased * (end - start)));
      if (p < 1) rafRef.current = requestAnimationFrame(tick);
      else prevRef.current = end;
    };
    rafRef.current = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(rafRef.current);
  }, [target, duration]);

  return value;
}

export default function Hero({ health, summary }) {
  const totalLogs = useCountUp(summary?.total_logs ?? 0);
  const totalAnomalies = useCountUp(summary?.total_anomalies ?? 0);
  const rate = Number(summary?.anomaly_rate ?? 0);

  const model = health?.model ?? '—';
  const embedding = health?.embedding_model ?? '—';
  const chromaDocs = health?.chroma_docs;

  return (
    <section className="hero" aria-label="Dashboard overview">
      {/* ── Left: copy ─────────────────────────────────────────── */}
      <div className="hero__copy">
        <div className="kicker">
          <span className="kicker__dot" aria-hidden="true" />
          AI-Powered · Security Intelligence
        </div>

        <h1 className="display">
          Detect threats<br />
          <span className="display__accent">in your logs.</span>
        </h1>

        <p className="lede">
          Ingest raw server logs, surface anomalies with ML scoring, and query
          your data with natural language — entirely offline.
        </p>

        <div className="hero__ctas">
          <a href="#ingest" className="btn btn-primary">
            Ingest Logs <span className="arrow" aria-hidden="true">→</span>
          </a>
          <a href="#ask" className="btn btn-ghost">
            Ask a Question
          </a>
        </div>
      </div>

      {/* ── Right: stats ───────────────────────────────────────── */}
      <div className="hero__stats" aria-label="Statistics">
        {/* Total logs */}
        <div className="stat-block">
          <div className="stat-block__num" aria-label={`${totalLogs} total logs`}>
            {totalLogs.toLocaleString()}
          </div>
          <div className="stat-block__lbl">Total Logs Ingested</div>
        </div>

        {/* Anomalies + rate */}
        <div className="stat-grid">
          <div className="stat-mini">
            <div className="stat-mini__num danger" aria-label={`${totalAnomalies} anomalies`}>
              {totalAnomalies.toLocaleString()}
            </div>
            <div className="stat-mini__lbl">Anomalies</div>
          </div>
          <div className="stat-mini">
            <div
              className={`stat-mini__num ${rate > 0.1 ? 'danger' : rate > 0.02 ? 'warning' : ''}`}
              aria-label={`${(rate * 100).toFixed(1)}% anomaly rate`}
            >
              {(rate * 100).toFixed(1)}%
            </div>
            <div className="stat-mini__lbl">Anomaly Rate</div>
          </div>
        </div>

        {/* Model metadata */}
        <div className="stat-meta">
          <div className="stat-meta__row">
            <span className="stat-meta__lbl">LLM</span>
            <span className="stat-meta__val">{model}</span>
          </div>
          <div className="stat-meta__row">
            <span className="stat-meta__lbl">Embedding</span>
            <span className="stat-meta__val">{embedding}</span>
          </div>
          <div className="stat-meta__row">
            <span className="stat-meta__lbl">Chunks</span>
            <span className="stat-meta__val">
              {chromaDocs != null ? Number(chromaDocs).toLocaleString() : '—'}
            </span>
          </div>
        </div>
      </div>
    </section>
  );
}
