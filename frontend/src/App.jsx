import React, { useState, useEffect, useCallback } from 'react';
import { fetchHealth, fetchAnomalySummary } from './api.js';
import Header from './components/Header.jsx';
import Hero from './components/Hero.jsx';
import UploadCard from './components/UploadCard.jsx';
import QueryCard from './components/QueryCard.jsx';
import AnomalyTable from './components/AnomalyTable.jsx';
import ToastContainer from './components/ToastContainer.jsx';

let _toastId = 0;

export default function App() {
  const [health, setHealth] = useState(null);
  const [summary, setSummary] = useState({
    total_logs: 0,
    total_anomalies: 0,
    anomaly_rate: 0,
  });
  const [toasts, setToasts] = useState([]);
  const [tableRefreshKey, setTableRefreshKey] = useState(0);
  const [activeUpload, setActiveUpload] = useState(null);

  // ── Toast helpers ──────────────────────────────────────────────────────────
  const addToast = useCallback((message, type = 'info', duration = 4000) => {
    const id = ++_toastId;
    setToasts((prev) => [...prev, { id, message, type, duration }]);
  }, []);

  const dismissToast = useCallback((id) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  // ── Poll health + summary every 10 s ──────────────────────────────────────
  const refreshStats = useCallback(async (uploadIdOverride = activeUpload?.upload_id) => {
    const summaryPromise = uploadIdOverride
      ? fetchAnomalySummary({ uploadId: uploadIdOverride })
      : Promise.resolve({
          total_logs: 0,
          total_anomalies: 0,
          anomaly_rate: 0,
        });
    const [h, s] = await Promise.allSettled([fetchHealth(), summaryPromise]);
    if (h.status === 'fulfilled') setHealth(h.value);
    else setHealth((prev) => prev ?? { status: 'error' });
    if (s.status === 'fulfilled') setSummary(s.value);
    setTableRefreshKey((k) => k + 1);
  }, [activeUpload?.upload_id]);

  useEffect(() => {
    refreshStats();
    const interval = setInterval(refreshStats, 10_000);
    return () => clearInterval(interval);
  }, [refreshStats]);

  // ── Ingest callbacks ───────────────────────────────────────────────────────
  const handleIngestSuccess = useCallback(
    (result) => {
      const count =
        result.ingested_lines ??
        result.logs_processed ??
        result.ingested ??
        result.count ??
        0;
      const chunks = result.chunks_stored ?? 0;
      setActiveUpload({
        upload_id: result.upload_id ?? null,
        source_name: result.source_name ?? 'Current upload',
        ingested_lines: count,
        chunks_stored: chunks,
      });
      addToast(
        `Ingested ${count} log ${count === 1 ? 'entry' : 'entries'} — ${chunks} chunks stored.`,
        'success'
      );
      refreshStats(result.upload_id ?? null);
    },
    [addToast, refreshStats]
  );

  return (
    <>
      {/* ── Background atmosphere ──────────────────────────────────── */}
      <div className="bg-orb bg-orb--a" aria-hidden="true" />
      <div className="bg-orb bg-orb--b" aria-hidden="true" />
      <div className="bg-grid" aria-hidden="true" />

      <Header health={health} />

      <main className="page">
        <Hero health={health} summary={summary} activeUpload={activeUpload} />

        <UploadCard
          onSuccess={handleIngestSuccess}
          onError={(msg) => addToast(msg, 'error', 6000)}
          onStatsChange={refreshStats}
        />

        <QueryCard
          activeUpload={activeUpload}
          onError={(msg) => addToast(msg, 'error', 6000)}
        />

        <AnomalyTable
          refreshKey={tableRefreshKey}
          uploadId={activeUpload?.upload_id ?? null}
        />
      </main>

      <footer className="foot">
        <span className="foot__mono">
          AI Security Log Analyst &mdash; TUS MSc Project &mdash; A00336067
        </span>
        <span className="foot__mono">Nitish Shankar Mudaliar</span>
      </footer>

      <ToastContainer toasts={toasts} onDismiss={dismissToast} />
    </>
  );
}
