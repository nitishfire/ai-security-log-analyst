"""
Tests for the log ingestion pipeline.

Covers:
  - Apache log line parsing
  - Malformed line handling
  - Chunking logic
  - File loading
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

from app.models.log_entry import LogEntry
from app.services.ingestion import chunk_logs, load_log_file
from app.utils.log_parser import parse_apache, parse_syslog, parse_kv, auto_detect_and_parse


# ── Fixtures ─────────────────────────────────────────────────────────────────

VALID_APACHE_LINE = (
    '192.168.1.1 - frank [10/Oct/2023:13:55:36 +0000] '
    '"GET /index.html HTTP/1.1" 200 2326 "-" "Mozilla/5.0"'
)

VALID_SYSLOG_LINE = (
    "May 26 14:30:01 myhost sshd[1234]: Failed password for root from 1.2.3.4 port 22 ssh2"
)

VALID_KV_LINE = (
    "2024-01-15T10:30:00Z INFO src_ip=192.168.1.10 status=200 path=/api/health"
)

MALFORMED_LINE = "this is not a log line at all @#$%"


# ── Apache parser ─────────────────────────────────────────────────────────────

class TestParseApache:
    def test_valid_line_returns_dict(self):
        result = parse_apache(VALID_APACHE_LINE)
        assert result is not None
        assert result["format_type"] == "apache"

    def test_source_ip_extracted(self):
        result = parse_apache(VALID_APACHE_LINE)
        assert result["source_ip"] == "192.168.1.1"

    def test_method_extracted(self):
        result = parse_apache(VALID_APACHE_LINE)
        assert result["method"] == "GET"

    def test_path_extracted(self):
        result = parse_apache(VALID_APACHE_LINE)
        assert result["path"] == "/index.html"

    def test_status_code_is_int(self):
        result = parse_apache(VALID_APACHE_LINE)
        assert result["status_code"] == 200

    def test_bytes_sent_is_int(self):
        result = parse_apache(VALID_APACHE_LINE)
        assert result["bytes_sent"] == 2326

    def test_malformed_returns_none(self):
        result = parse_apache(MALFORMED_LINE)
        assert result is None

    def test_empty_string_returns_none(self):
        assert parse_apache("") is None


# ── Syslog parser ─────────────────────────────────────────────────────────────

class TestParseSyslog:
    def test_valid_line_returns_dict(self):
        result = parse_syslog(VALID_SYSLOG_LINE)
        assert result is not None
        assert result["format_type"] == "syslog"

    def test_timestamp_extracted(self):
        result = parse_syslog(VALID_SYSLOG_LINE)
        assert result["timestamp"] is not None
        assert "14:30:01" in result["timestamp"]

    def test_hostname_extracted(self):
        result = parse_syslog(VALID_SYSLOG_LINE)
        assert result["hostname"] == "myhost"

    def test_process_extracted(self):
        result = parse_syslog(VALID_SYSLOG_LINE)
        assert result["process"] == "sshd"

    def test_ip_in_message_extracted(self):
        result = parse_syslog(VALID_SYSLOG_LINE)
        assert result["source_ip"] == "1.2.3.4"

    def test_error_level_for_failed(self):
        result = parse_syslog(VALID_SYSLOG_LINE)
        assert result["log_level"] == "ERROR"


# ── KV parser ─────────────────────────────────────────────────────────────────

class TestParseKV:
    def test_valid_line_returns_dict(self):
        result = parse_kv(VALID_KV_LINE)
        assert result is not None
        assert result["format_type"] == "kv"

    def test_timestamp_extracted(self):
        result = parse_kv(VALID_KV_LINE)
        assert "2024-01-15" in result["timestamp"]

    def test_level_extracted(self):
        result = parse_kv(VALID_KV_LINE)
        assert result["log_level"] == "INFO"

    def test_source_ip_from_kv(self):
        result = parse_kv(VALID_KV_LINE)
        assert result["source_ip"] == "192.168.1.10"


# ── Auto-detect ───────────────────────────────────────────────────────────────

class TestAutoDetect:
    def test_detects_apache(self):
        result = auto_detect_and_parse(VALID_APACHE_LINE)
        assert result is not None
        assert result["format_type"] == "apache"

    def test_detects_syslog(self):
        result = auto_detect_and_parse(VALID_SYSLOG_LINE)
        assert result is not None
        assert result["format_type"] == "syslog"

    def test_detects_kv(self):
        result = auto_detect_and_parse(VALID_KV_LINE)
        assert result is not None
        assert result["format_type"] == "kv"

    def test_blank_line_returns_none(self):
        assert auto_detect_and_parse("") is None

    def test_comment_line_returns_none(self):
        assert auto_detect_and_parse("# this is a comment") is None


# ── LogEntry model ────────────────────────────────────────────────────────────

class TestLogEntry:
    def test_from_apache_parsed_dict(self):
        data = parse_apache(VALID_APACHE_LINE)
        entry = LogEntry.from_parsed_dict(data)
        assert entry.source_ip == "192.168.1.1"
        assert entry.status_code == 200
        assert entry.method == "GET"
        assert entry.path == "/index.html"

    def test_to_chunk_text_nonempty(self):
        data = parse_apache(VALID_APACHE_LINE)
        entry = LogEntry.from_parsed_dict(data)
        text = entry.to_chunk_text()
        assert len(text) > 10
        assert "192.168.1.1" in text

    def test_invalid_ip_accepted(self):
        """Non-IP values should be stored as-is (parser is lenient)."""
        entry = LogEntry(source_ip="not-an-ip", message="test", raw="test")
        assert entry.source_ip == "not-an-ip"


# ── Chunk logs ────────────────────────────────────────────────────────────────

class TestChunkLogs:
    def _make_entries(self, n: int) -> list:
        return [
            LogEntry(
                message=f"Log line number {i} with some content to fill up chars",
                raw=f"raw line {i}",
            )
            for i in range(n)
        ]

    def test_empty_entries_returns_empty(self):
        assert chunk_logs([]) == []

    def test_100_entries_creates_chunks(self):
        entries = self._make_entries(100)
        chunks = chunk_logs(entries, chunk_size=500, overlap=50)
        assert len(chunks) > 0

    def test_chunk_count_reasonable(self):
        """With 100 short entries and chunk_size=500, expect several chunks."""
        entries = self._make_entries(100)
        chunks = chunk_logs(entries, chunk_size=500, overlap=50)
        # Each entry is ~60 chars; 500/60 ≈ 8 per chunk → ~12-15 chunks
        assert 5 <= len(chunks) <= 50

    def test_no_empty_chunks(self):
        entries = self._make_entries(50)
        chunks = chunk_logs(entries, chunk_size=500, overlap=50)
        for chunk in chunks:
            assert chunk.strip() != ""

    def test_single_entry_one_chunk(self):
        entries = self._make_entries(1)
        chunks = chunk_logs(entries, chunk_size=500, overlap=50)
        assert len(chunks) == 1


# ── Load log file ─────────────────────────────────────────────────────────────

class TestLoadLogFile:
    def test_nonexistent_file_raises(self):
        with pytest.raises(FileNotFoundError):
            load_log_file("/nonexistent/path/file.log")

    def test_wrong_extension_raises(self):
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
            f.write(b"data\n")
            tmp = f.name
        try:
            with pytest.raises(ValueError, match="Unsupported file type"):
                load_log_file(tmp)
        finally:
            os.unlink(tmp)

    def test_loads_apache_log(self):
        sample = Path("data/raw_logs/sample_access.log")
        if not sample.exists():
            pytest.skip("sample_access.log not generated yet — run scripts/generate_sample_logs.py")
        entries = load_log_file(str(sample))
        assert len(entries) > 100

    def test_skips_blank_and_comment_lines(self):
        content = "\n".join([
            "# comment",
            "",
            VALID_APACHE_LINE,
            "",
            VALID_APACHE_LINE,
        ])
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".log", delete=False, encoding="utf-8"
        ) as f:
            f.write(content)
            tmp = f.name
        try:
            entries = load_log_file(tmp)
            assert len(entries) == 2
        finally:
            os.unlink(tmp)

    def test_malformed_lines_skipped_gracefully(self):
        content = "\n".join([
            VALID_APACHE_LINE,
            "MALFORMED @@@ LINE",
            VALID_APACHE_LINE,
        ])
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".log", delete=False, encoding="utf-8"
        ) as f:
            f.write(content)
            tmp = f.name
        try:
            # Should not raise; malformed line parsed as 'unknown' format
            entries = load_log_file(tmp)
            assert len(entries) >= 2
        finally:
            os.unlink(tmp)
