import React from 'react';

/**
 * React Error Boundary — catches unhandled render/lifecycle errors in the
 * component tree below it and renders a recovery UI instead of crashing the
 * whole page.
 *
 * Usage:
 *   <ErrorBoundary>
 *     <App />
 *   </ErrorBoundary>
 */
export default class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }

  componentDidCatch(error, errorInfo) {
    // In production you'd send this to an error tracker (Sentry, etc.)
    console.error('[ErrorBoundary] Uncaught error:', error, errorInfo);
  }

  handleReset = () => {
    this.setState({ hasError: false, error: null });
  };

  render() {
    if (!this.state.hasError) {
      return this.props.children;
    }

    return (
      <div
        role="alert"
        style={{
          minHeight: '100vh',
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          gap: '20px',
          padding: '40px',
          background: '#000',
          color: '#eeeaf6',
          fontFamily: 'var(--sans, system-ui)',
          textAlign: 'center',
        }}
      >
        <div
          aria-hidden="true"
          style={{
            width: '52px',
            height: '52px',
            borderRadius: '50%',
            border: '1.5px solid oklch(70% 0.20 25 / .5)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            fontSize: '1.4rem',
            color: 'oklch(70% 0.20 25)',
          }}
        >
          !
        </div>

        <h2 style={{ fontSize: '1.2rem', fontWeight: 500, color: 'oklch(70% 0.20 25)' }}>
          Something went wrong
        </h2>

        <p style={{ maxWidth: '42ch', color: '#b8b3c8', fontSize: '.88rem', lineHeight: 1.55 }}>
          {this.state.error?.message || 'An unexpected rendering error occurred.'}
        </p>

        <button
          onClick={this.handleReset}
          style={{
            padding: '10px 22px',
            background: 'oklch(72% 0.21 295)',
            color: '#0a0413',
            border: 'none',
            borderRadius: '999px',
            cursor: 'pointer',
            fontSize: '.84rem',
            fontWeight: 500,
            transition: 'background 200ms',
          }}
          onMouseEnter={(e) => (e.target.style.background = 'oklch(82% 0.18 295)')}
          onMouseLeave={(e) => (e.target.style.background = 'oklch(72% 0.21 295)')}
        >
          Try again
        </button>
      </div>
    );
  }
}
