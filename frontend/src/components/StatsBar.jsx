import React from 'react';
import { useCountUp } from '../hooks/useCountUp.js';

function StatCard({ label, value, icon, accent }) {
  const display = useCountUp(typeof value === 'number' ? value : 0);

  return (
    <div className={`stat-card ${accent ? 'stat-card--accent' : ''}`}>
      <div className="stat-icon" aria-hidden="true">
        {icon}
      </div>
      <div className="stat-body">
        <span
          className="stat-value"
          data-string={typeof value !== 'number' ? 'true' : undefined}
        >
          {typeof value === 'number' ? display.toLocaleString() : value ?? '—'}
        </span>
        <span className="stat-label">{label}</span>
      </div>
    </div>
  );
}

export default function StatsBar({ stats }) {
  const logsIngested = stats?.logs_ingested ?? 0;
  const anomaliesFound = stats?.anomalies_found ?? 0;
  const queriesRun = stats?.queries_run ?? 0;
  const modelStatus = stats?.model_status ?? 'unknown';

  return (
    <div className="stats-bar">
      <StatCard
        label="Logs Ingested"
        value={logsIngested}
        icon={
          <svg viewBox="0 0 20 20" fill="none">
            <path
              d="M4 4h12M4 8h12M4 12h8"
              stroke="currentColor"
              strokeWidth="1.5"
              strokeLinecap="round"
            />
          </svg>
        }
      />
      <StatCard
        label="Anomalies Found"
        value={anomaliesFound}
        accent
        icon={
          <svg viewBox="0 0 20 20" fill="none">
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
        }
      />
      <StatCard
        label="Queries Run"
        value={queriesRun}
        icon={
          <svg viewBox="0 0 20 20" fill="none">
            <circle cx="9" cy="9" r="5" stroke="currentColor" strokeWidth="1.5" />
            <path
              d="M15 15l-3-3"
              stroke="currentColor"
              strokeWidth="1.5"
              strokeLinecap="round"
            />
          </svg>
        }
      />
      <StatCard
        label="Model Status"
        value={modelStatus}
        icon={
          <svg viewBox="0 0 20 20" fill="none">
            <rect
              x="3"
              y="6"
              width="14"
              height="9"
              rx="2"
              stroke="currentColor"
              strokeWidth="1.5"
            />
            <path
              d="M7 6V4h6v2"
              stroke="currentColor"
              strokeWidth="1.5"
              strokeLinecap="round"
            />
          </svg>
        }
      />
    </div>
  );
}
