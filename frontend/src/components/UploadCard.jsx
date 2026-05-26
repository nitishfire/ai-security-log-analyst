import React, { useState, useRef, useCallback } from 'react';
import { ingestFile, ingestText } from '../api.js';

const PREVIEW_LINES = 10;
const PREVIEW_BYTES = 16 * 1024;
const MAX_FILE_BYTES = 10 * 1024 * 1024; // 10 MB — mirrors backend limit

function readFilePreview(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const text = String(reader.result || '');
      resolve(text.split(/\r?\n/).slice(0, PREVIEW_LINES).join('\n'));
    };
    reader.onerror = () => reject(reader.error || new Error('Could not read file preview'));
    reader.readAsText(file.slice(0, PREVIEW_BYTES));
  });
}

export default function UploadCard({ onSuccess, onError, onStatsChange }) {
  const [mode, setMode] = useState('file'); // 'file' | 'text'
  const [dragging, setDragging] = useState(false);
  const [loading, setLoading] = useState(false);
  const [textValue, setTextValue] = useState('');
  const [selectedFile, setSelectedFile] = useState(null);
  const [filePreview, setFilePreview] = useState('');
  const [ingestResult, setIngestResult] = useState(null);
  const fileInputRef = useRef(null);

  const selectFile = useCallback(
    async (file) => {
      // Client-side size guard — gives immediate feedback before upload starts
      if (file.size > MAX_FILE_BYTES) {
        onError(
          `File is too large (${(file.size / 1024 / 1024).toFixed(1)} MB). Maximum is 10 MB.`
        );
        return;
      }
      setSelectedFile(file);
      setFilePreview('');
      setIngestResult(null);
      try {
        setFilePreview(await readFilePreview(file));
      } catch (err) {
        onError(err.message || 'Could not preview file');
      }
    },
    [onError]
  );

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
        setIngestResult(result);
        onSuccess(result);
        onStatsChange?.();
        setTextValue('');
        setSelectedFile(null);
        setFilePreview('');
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
  const onDragOver = (e) => { e.preventDefault(); setDragging(true); };
  const onDragLeave = () => setDragging(false);
  const onDrop = (e) => {
    e.preventDefault();
    setDragging(false);
    const file = e.dataTransfer.files?.[0];
    if (file) { setMode('file'); selectFile(file); }
  };
  const onFileChange = (e) => {
    const file = e.target.files?.[0];
    if (file) selectFile(file);
  };

  const clearAll = () => {
    setSelectedFile(null);
    setFilePreview('');
    setTextValue('');
    setIngestResult(null);
    if (fileInputRef.current) fileInputRef.current.value = '';
  };

  return (
    <section className="block" id="ingest">
      {/* ── Block header ────────────────────────────────────────── */}
      <div className="block__head">
        <span className="block__num">01</span>
        <h2 className="block__title">Ingest</h2>
        <span className="block__hint">.log · .txt</span>
        {/* Mode tabs — has margin-left: auto in CSS */}
        <div className="mode-tabs" role="group" aria-label="Input mode">
          <button
            className={`mode-tab${mode === 'file' ? ' active' : ''}`}
            onClick={() => setMode('file')}
            type="button"
          >
            File
          </button>
          <button
            className={`mode-tab${mode === 'text' ? ' active' : ''}`}
            onClick={() => setMode('text')}
            type="button"
          >
            Text
          </button>
        </div>
      </div>

      {/* ── 2-column ingest grid ─────────────────────────────────── */}
      <div className="ingest">
        {/* Col 1: drop zone or textarea */}
        {mode === 'file' ? (
          <div
            className={`drop-zone${dragging ? ' drag-over' : ''}`}
            onDragOver={onDragOver}
            onDragLeave={onDragLeave}
            onDrop={onDrop}
            onClick={() => fileInputRef.current?.click()}
            role="button"
            tabIndex={0}
            aria-label="Click or drag a log file to upload"
            onKeyDown={(e) => e.key === 'Enter' && fileInputRef.current?.click()}
          >
            <div className="drop-zone__icon" aria-hidden="true">
              <svg viewBox="0 0 24 24" fill="none" width="22" height="22">
                <path
                  d="M12 3v13M7 8l5-5 5 5M3 19h18"
                  stroke="currentColor"
                  strokeWidth="1.5"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              </svg>
            </div>
            <div className="drop-zone__text">
              {selectedFile ? (
                <>
                  <strong>{selectedFile.name}</strong>
                  <span>
                    {(selectedFile.size / 1024).toFixed(1)} KB
                    <span> — click to change</span>
                  </span>
                </>
              ) : (
                <>
                  <strong>Drop a .log or .txt file here</strong>
                  <span>or click to browse</span>
                </>
              )}
            </div>
            <input
              ref={fileInputRef}
              type="file"
              accept=".log,.txt"
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
            aria-label="Paste log text"
          />
        )}

        {/* Col 2: action buttons */}
        <div className="ingest__actions">
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
              <><span className="spinner" aria-hidden="true" /> Ingesting…</>
            ) : (
              'Ingest Logs'
            )}
          </button>

          {(selectedFile || textValue || ingestResult) && (
            <button
              className="btn btn-ghost"
              type="button"
              onClick={clearAll}
            >
              Clear
            </button>
          )}
        </div>

        {/* Full-width file preview (grid-column: 1 / -1 in CSS) */}
        {mode === 'file' && selectedFile && filePreview && (
          <div className="file-preview">
            <div className="file-preview-head">
              <span>{selectedFile.name}</span>
              <span>First {PREVIEW_LINES} lines</span>
            </div>
            <pre>{filePreview}</pre>
          </div>
        )}

        {/* Full-width ingest result (grid-column: 1 / -1 in CSS) */}
        <div className={`ingest-result-strip${ingestResult ? ' show' : ''}`} aria-live="polite">
          {ingestResult && (
            <div className="ingest-result">
              <div className="ingest-result-item">
                <div className="num">
                  {ingestResult.ingested_lines ??
                    ingestResult.logs_processed ??
                    ingestResult.ingested ??
                    ingestResult.count ??
                    0}
                </div>
                <div className="lbl">Lines</div>
              </div>
              <div className="ingest-result-item">
                <div className="num">{ingestResult.chunks_stored ?? 0}</div>
                <div className="lbl">Chunks</div>
              </div>
              <div className="ingest-result-item">
                <div className="num">{ingestResult.anomalies_found ?? 0}</div>
                <div className="lbl">Anomalies</div>
              </div>
              <div className="ingest-result-item">
                <div className="num" style={{ color: 'var(--success)' }}>✓</div>
                <div className="lbl">Stored</div>
              </div>
            </div>
          )}
        </div>
      </div>
    </section>
  );
}
