import React, { useState, useRef, useCallback } from 'react';
import { ingestFile, ingestText } from '../api.js';
import { useMouseGlow } from '../hooks/useMouseGlow.js';

export default function UploadCard({ onSuccess, onError, onStatsChange }) {
  const [mode, setMode] = useState('file'); // 'file' | 'text'
  const [dragging, setDragging] = useState(false);
  const [loading, setLoading] = useState(false);
  const [textValue, setTextValue] = useState('');
  const [selectedFile, setSelectedFile] = useState(null);
  const fileInputRef = useRef(null);
  const handleGlow = useMouseGlow();

  const submit = useCallback(
    async (file, text) => {
      if (loading) return;
      setLoading(true);
      try {
        let result;
        if (mode === 'file' && file) {
          result = await ingestFile(file);
        } else if (mode === 'text' && text.trim()) {
          result = await ingestText(text.trim());
        } else {
          onError('Nothing to ingest — select a file or paste log text.');
          setLoading(false);
          return;
        }
        onSuccess(result);
        onStatsChange?.();
        setTextValue('');
        setSelectedFile(null);
        if (fileInputRef.current) fileInputRef.current.value = '';
      } catch (err) {
        onError(err.message || 'Ingest failed');
      } finally {
        setLoading(false);
      }
    },
    [loading, mode, onSuccess, onError, onStatsChange]
  );

  // ── Drag-and-drop ────────────────────────────────────────────────────────
  const onDragOver = (e) => {
    e.preventDefault();
    setDragging(true);
  };
  const onDragLeave = () => setDragging(false);
  const onDrop = (e) => {
    e.preventDefault();
    setDragging(false);
    const file = e.dataTransfer.files?.[0];
    if (file) {
      setSelectedFile(file);
      setMode('file');
      submit(file, '');
    }
  };

  const onFileChange = (e) => {
    const file = e.target.files?.[0];
    if (file) setSelectedFile(file);
  };

  return (
    <div className="card" onMouseMove={handleGlow}>
      <div className="card-header">
        <h2 className="card-title">
          <svg viewBox="0 0 20 20" fill="none" className="card-title-icon" aria-hidden="true">
            <path
              d="M10 3v10M6 9l4-6 4 6"
              stroke="currentColor"
              strokeWidth="1.5"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
            <path
              d="M3 15h14"
              stroke="currentColor"
              strokeWidth="1.5"
              strokeLinecap="round"
            />
          </svg>
          Ingest Logs
        </h2>

        {/* Mode toggle */}
        <div className="toggle-group" role="group" aria-label="Input mode">
          <button
            className={`toggle-btn ${mode === 'file' ? 'active' : ''}`}
            onClick={() => setMode('file')}
            type="button"
          >
            File
          </button>
          <button
            className={`toggle-btn ${mode === 'text' ? 'active' : ''}`}
            onClick={() => setMode('text')}
            type="button"
          >
            Text
          </button>
        </div>
      </div>

      <div className="card-body">
        {mode === 'file' ? (
          <div
            className={`drop-zone ${dragging ? 'drop-zone--active' : ''}`}
            onDragOver={onDragOver}
            onDragLeave={onDragLeave}
            onDrop={onDrop}
            onClick={() => fileInputRef.current?.click()}
            role="button"
            tabIndex={0}
            aria-label="Click or drag a log file to upload"
            onKeyDown={(e) => e.key === 'Enter' && fileInputRef.current?.click()}
          >
            <svg
              className="drop-zone-icon"
              viewBox="0 0 48 48"
              fill="none"
              aria-hidden="true"
            >
              <path
                d="M8 36h32M24 12v20M16 20l8-8 8 8"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
            {selectedFile ? (
              <p className="drop-zone-text">
                <strong>{selectedFile.name}</strong>
                <br />
                <span className="drop-zone-hint">
                  {(selectedFile.size / 1024).toFixed(1)} KB — click to change
                </span>
              </p>
            ) : (
              <p className="drop-zone-text">
                Drop a <strong>.log</strong> file here
                <br />
                <span className="drop-zone-hint">or click to browse</span>
              </p>
            )}
            <input
              ref={fileInputRef}
              type="file"
              accept=".log,.txt,.json"
              className="sr-only"
              onChange={onFileChange}
              aria-hidden="true"
            />
          </div>
        ) : (
          <textarea
            className="log-textarea"
            rows={8}
            placeholder="Paste raw log lines here…"
            value={textValue}
            onChange={(e) => setTextValue(e.target.value)}
            spellCheck={false}
          />
        )}

        <button
          className="btn btn-primary"
          onClick={() => submit(selectedFile, textValue)}
          disabled={
            loading ||
            (mode === 'file' && !selectedFile) ||
            (mode === 'text' && !textValue.trim())
          }
          type="button"
        >
          {loading ? (
            <>
              <span className="spinner" aria-hidden="true" />
              Ingesting…
            </>
          ) : (
            'Ingest Logs'
          )}
        </button>
      </div>
    </div>
  );
}
