import React, { useState, useEffect, useCallback, useId } from 'react';
import { fetchHealth, fetchAnomalies } from './api.js';
import Header from './components/Header.jsx';
import StatsBar from './components/StatsBar.jsx';
import UploadCard from './components/UploadCard.jsx';
import QueryCard from './components/QueryCard.jsx';
import AnomalyTable from './components/AnomalyTable.jsx';
import ToastContainer from './components/ToastContainer.jsx';

let _toastId = 0;

export default function App() {
  const [health, setHealth] = useState(null);
  const [stats, setStats] = useState({
    logs_ingested: 0,
    anomalies_found: 0,
    queries_run: 0,
    model_status: 'loading',
  });
  const [toasts, setToasts] = useState([]);
  const [tableRefreshKey, setTableRefreshKey] = useState(0);

  // ── Toast helpers ──────────────────────────────────────────────────────────
  const addToast = useCallback((message, type = 'info', duration = 4000) => {
    const id = ++_toastId;
    setToasts((prev) => [...prev, { id, message, type, duration }]);
  }, []);

  const dismissToast = useCallback((id) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  // ── Health poll ────────────────────────────────────────────────────────────
  useEffect(() => {
    let mounted = true;
    const poll = async () => {
      try {
        const h = await fetchHealth();
        if (mounted) setHealth(h);
      } catch (_) {
        if (mounted) setHealth({ status: 'error' });
      }
    };
    poll();
    const interval = setInterval(poll, 30_000);
    return () => {
      mounted = false;
      clearInterval(interval);
    };
  }, []);

  // ── Stats refresh ──────────────────────────────────────────────────────────
  const refreshStats = useCallback(async () => {
    try {
      const data = await fetchAnomalies({ limit: 1 });
      const total = data.total ?? 0;
      setStats((prev) => ({
        ...prev,
        anomalies_found: total,
        model_status: 'ready',
      }));
      setTableRefreshKey((k) => k + 1);
    } catch (_) {
      // silently ignore — stats are best-effort
    }
  }, []);

  useEffect(() => {
    refreshStats();
  }, [refreshStats]);

  // ── Ingest callbacks ───────────────────────────────────────────────────────
  const handleIngestSuccess = useCallback(
    (result) => {
      const count = result.logs_processed ?? result.ingested ?? result.count ?? '?';
      addToast(`Ingested ${count} log entries successfully.`, 'success');
      setStats((prev) => ({
        ...prev,
        logs_ingested: prev.logs_ingested + (Number(count) || 0),
      }));
      refreshStats();
    },
    [addToast, refreshStats]
  );

  const handleIngestError = useCallback(
    (msg) => addToast(msg, 'error', 6000),
    [addToast]
  );

  const handleQueryError = useCallback(
    (msg) => addToast(msg, 'error', 6000),
    [addToast]
  );

  const handleQuerySuccess = useCallback(() => {
    setStats((prev) => ({ ...prev, queries_run: prev.queries_run + 1 }));
  }, []);

  // Expose handleQuerySuccess so QueryCard can call it:
  // We pass it wrapped inside a combined error handler
  const handleQueryErrorWrapper = useCallback(
    (msg) => {
      if (!msg) {
        // called on success (from a previous design) — increment counter
        handleQuerySuccess();
      } else {
        handleQueryError(msg);
      }
    },
    [handleQueryError, handleQuerySuccess]
  );

  return (
    <>
      {/* ── Aurora background layers ── */}
      <div className="aurora" aria-hidden="true" />
      <div className="star-noise" aria-hidden="true" />

      <Header health={health} />

      <main className="main">
        <StatsBar stats={stats} />

        <div className="grid">
          <UploadCard
            onSuccess={handleIngestSuccess}
            onError={handleIngestError}
            onStatsChange={refreshStats}
          />
          <QueryCard onError={handleQueryErrorWrapper} />
        </div>

        <AnomalyTable refreshKey={tableRefreshKey} />
      </main>

      <footer className="footer">
        <p>
          AI Security Log Analyst &mdash; TUS MSc Project &mdash; A00336067 Nitish Shankar Mudaliar
        </p>
      </footer>

      <ToastContainer toasts={toasts} onDismiss={dismissToast} />
    </>
  );
}
