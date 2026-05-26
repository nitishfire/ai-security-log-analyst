"""
Tests for the anomaly detection service.

Covers:
  - Feature extraction from LogEntry
  - IsolationForest fit + predict
  - Anomaly score range
"""

from __future__ import annotations

import random
from datetime import datetime
from typing import List

import pytest

from app.models.log_entry import LogEntry
from app.services.anomaly_detector import (
    AnomalyDetector,
    AnomalyResult,
    extract_features,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _normal_entry(i: int = 0) -> LogEntry:
    """Create a realistic normal log entry."""
    return LogEntry(
        timestamp=datetime(2024, 6, 1, 10, 0, i % 60),
        source_ip=f"192.168.1.{(i % 50) + 10}",
        method="GET",
        path="/index.html",
        status_code=200,
        bytes_sent=random.randint(500, 10_000),
        log_level="INFO",
        message="GET /index.html -> 200",
        raw="raw line",
        format_type="apache",
    )


def _anomalous_entry(i: int = 0) -> LogEntry:
    """Create a clearly anomalous log entry (SQL injection + huge bytes)."""
    return LogEntry(
        timestamp=datetime(2024, 6, 1, 3, 0, i % 60),   # 3 AM
        source_ip="1.2.3.4",
        method="POST",
        path="/login?user=admin'--",
        status_code=500,
        bytes_sent=50_000_000,   # 50 MB response = anomalous
        log_level="ERROR",
        message="SQL injection attempt",
        raw="raw line",
        format_type="apache",
    )


def _suspicious_entry(i: int = 0) -> LogEntry:
    """Suspicious but not necessarily anomalous."""
    return LogEntry(
        timestamp=datetime(2024, 6, 1, 14, 30, i % 60),
        source_ip="10.0.0.1",
        method="GET",
        path="/admin",
        status_code=403,
        bytes_sent=256,
        log_level="WARNING",
        message="GET /admin -> 403",
        raw="raw line",
        format_type="apache",
    )


# ── Feature extraction ────────────────────────────────────────────────────────

class TestFeatureExtraction:
    def test_returns_dict(self):
        entry = _normal_entry()
        feat = extract_features(entry)
        assert isinstance(feat, dict)

    def test_required_keys_present(self):
        entry = _normal_entry()
        feat = extract_features(entry)
        expected = {
            "status_code", "bytes_sent", "bytes_log", "is_post", "is_error",
            "path_depth", "has_suspicious_path", "hour_of_day", "request_rate_1min",
        }
        assert expected.issubset(feat.keys())

    def test_all_values_are_numeric(self):
        entry = _normal_entry()
        feat = extract_features(entry)
        for k, v in feat.items():
            assert isinstance(v, (int, float)), f"Feature '{k}' is not numeric: {v!r}"

    def test_is_post_flag(self):
        post_entry = LogEntry(method="POST", path="/api", status_code=200, raw="x", message="x")
        get_entry  = LogEntry(method="GET",  path="/api", status_code=200, raw="x", message="x")
        assert extract_features(post_entry)["is_post"] == 1.0
        assert extract_features(get_entry)["is_post"]  == 0.0

    def test_is_error_flag(self):
        err_entry = LogEntry(method="GET", path="/api", status_code=500, raw="x", message="x")
        ok_entry  = LogEntry(method="GET", path="/api", status_code=200, raw="x", message="x")
        assert extract_features(err_entry)["is_error"] == 1.0
        assert extract_features(ok_entry)["is_error"]  == 0.0

    def test_suspicious_path_detected(self):
        sus = LogEntry(method="GET", path="/admin/panel", status_code=403, raw="x", message="x")
        norm = LogEntry(method="GET", path="/index.html", status_code=200, raw="x", message="x")
        assert extract_features(sus)["has_suspicious_path"] == 1.0
        assert extract_features(norm)["has_suspicious_path"] == 0.0

    def test_path_depth_counted(self):
        entry = LogEntry(method="GET", path="/a/b/c/d", status_code=200, raw="x", message="x")
        feat = extract_features(entry)
        assert feat["path_depth"] == 4.0

    def test_hour_of_day_extracted(self):
        entry = _normal_entry()  # timestamp set to 10:00
        feat = extract_features(entry)
        assert feat["hour_of_day"] == 10.0

    def test_hour_defaults_when_no_timestamp(self):
        entry = LogEntry(message="no ts", raw="x")
        feat = extract_features(entry)
        assert feat["hour_of_day"] == 12.0   # neutral default


# ── Fit and predict ───────────────────────────────────────────────────────────

class TestFitPredict:
    def _build_dataset(self, n_normal: int = 100, n_anomalous: int = 10) -> List[LogEntry]:
        random.seed(42)
        entries = [_normal_entry(i) for i in range(n_normal)]
        entries += [_anomalous_entry(i) for i in range(n_anomalous)]
        random.shuffle(entries)
        return entries

    def test_fit_does_not_raise(self):
        detector = AnomalyDetector()
        entries = self._build_dataset()
        detector.fit(entries)   # Should complete without error
        assert detector.is_fitted

    def test_predict_returns_correct_count(self):
        detector = AnomalyDetector()
        entries = self._build_dataset()
        detector.fit(entries)
        results = detector.predict(entries)
        assert len(results) == len(entries)

    def test_predict_returns_anomaly_results(self):
        detector = AnomalyDetector()
        entries = self._build_dataset()
        detector.fit(entries)
        results = detector.predict(entries)
        for r in results:
            assert isinstance(r, AnomalyResult)
            assert isinstance(r.is_anomaly, bool)
            assert isinstance(r.anomaly_score, float)

    def test_some_anomalies_flagged(self):
        """At least some of the injected anomalous entries should be flagged."""
        detector = AnomalyDetector()
        entries = self._build_dataset(n_normal=100, n_anomalous=10)
        detector.fit(entries)
        results = detector.predict(entries)
        anomaly_count = sum(1 for r in results if r.is_anomaly)
        assert anomaly_count > 0, "Expected at least one anomaly to be flagged"

    def test_fit_on_empty_raises(self):
        detector = AnomalyDetector()
        with pytest.raises(ValueError):
            detector.fit([])

    def test_predict_without_fit_raises(self):
        detector = AnomalyDetector()
        with pytest.raises(RuntimeError):
            detector.predict([_normal_entry()])


# ── Anomaly score range ───────────────────────────────────────────────────────

class TestAnomalyScoreRange:
    def test_scores_between_minus1_and_plus1(self):
        random.seed(0)
        detector = AnomalyDetector()
        entries = [_normal_entry(i) for i in range(80)] + [_anomalous_entry(i) for i in range(20)]
        detector.fit(entries)
        results = detector.predict(entries)
        for r in results:
            assert -1.0 <= r.anomaly_score <= 1.0, (
                f"Score {r.anomaly_score} out of [-1, 1] range"
            )

    def test_features_dict_in_result(self):
        detector = AnomalyDetector()
        entries = [_normal_entry(i) for i in range(50)] + [_anomalous_entry(i) for i in range(5)]
        detector.fit(entries)
        results = detector.predict(entries[:5])
        for r in results:
            assert isinstance(r.features, dict)
            assert "status_code" in r.features
