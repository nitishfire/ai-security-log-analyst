import React from 'react';

export default function Header({ health }) {
  const online = health?.status === 'ok';

  return (
    <header className="header">
      <div className="header-inner">
        <div className="logo">
          {/* Shield icon */}
          <svg
            className="logo-icon"
            viewBox="0 0 24 24"
            fill="none"
            aria-hidden="true"
          >
            <path
              d="M12 2L3 6.5V12c0 5 3.8 9.7 9 10.9C17.2 21.7 21 17 21 12V6.5L12 2Z"
              stroke="currentColor"
              strokeWidth="1.5"
              strokeLinejoin="round"
              fill="oklch(0.55 0.28 275 / 0.15)"
            />
            <path
              d="M9 12l2 2 4-4"
              stroke="currentColor"
              strokeWidth="1.5"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
          <span className="logo-text">
            AI Security <span className="logo-accent">Log Analyst</span>
          </span>
        </div>

        <div className="header-right">
          <span
            className={`status-badge ${online ? 'status-online' : 'status-offline'}`}
            title={online ? 'Backend online' : 'Backend offline'}
          >
            <span className="status-dot" />
            {online ? 'Online' : 'Offline'}
          </span>
        </div>
      </div>
    </header>
  );
}
