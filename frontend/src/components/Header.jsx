import React from 'react';

export default function Header({ health }) {
  const online = health?.status === 'ok';

  return (
    <header className="rail">
      {/* ── Brand ─────────────────────────────────────────────── */}
      <div className="rail__brand">
        <div className="brand-mark" aria-hidden="true" />
        <div className="brand-text">
          <span className="brand-title">Log Analyst</span>
          <span className="brand-sub">AI Security · TUS MSc</span>
        </div>
      </div>

      {/* ── Nav ───────────────────────────────────────────────── */}
      <nav className="rail__nav" aria-label="Page sections">
        <a href="#ingest" className="rail__link">
          <span style={{ color: 'var(--violet-hi)', fontFamily: 'var(--mono)', fontSize: '.7rem' }}>01</span>
          {' '}Ingest
        </a>
        <a href="#ask" className="rail__link">
          <span style={{ color: 'var(--violet-hi)', fontFamily: 'var(--mono)', fontSize: '.7rem' }}>02</span>
          {' '}Ask
        </a>
        <a href="#anomalies" className="rail__link">
          <span style={{ color: 'var(--violet-hi)', fontFamily: 'var(--mono)', fontSize: '.7rem' }}>03</span>
          {' '}Anomalies
        </a>
      </nav>

      {/* ── Status ────────────────────────────────────────────── */}
      <div className="status-indicator" title={online ? 'Backend online' : 'Backend offline'}>
        <span className={`status-dot ${health ? (online ? 'online' : 'offline') : ''}`} aria-hidden="true" />
        <span>{health ? (online ? 'Online' : 'Offline') : 'Connecting…'}</span>
      </div>
    </header>
  );
}
