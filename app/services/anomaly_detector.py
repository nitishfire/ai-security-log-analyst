"""
Anomaly detection service using scikit-learn Isolation Forest.

Features extracted per log entry:
  - status_code          HTTP status (0 for syslog/kv entries)
  - bytes_sent           Response bytes (0 if absent)
  - is_post              1 if HTTP method is POST, else 0
  - is_error             1 if status >= 400, else 0
  - path_depth           Number of '/' chars in URL path
  - has_suspicious_path  1 if path contains known dangerous keywords
  - hour_of_day          0-23 from timestamp (12 if absent)
  - request_rate_1min    Rolling count of requests from same IP in the batch
                         (approximated as per-batch frequency)

The trained model is persisted to the path configured in ANOMALY_MODEL_PATH.
A SHA-256 digest file (.sha256) is written alongside the model and verified
on every load to detect accidental or malicious tampering.
"""

from __future__ import annotations

import hashlib
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import joblib
import numpy as np
from sklearn.ensemble import IsolationForest

from app.core.config import get_settings
from app.core.logger import get_logger
from app.models.log_entry import LogEntry

logger = get_logger(__name__)

# Keywords that indicate suspicious / high-risk URL paths
_SUSPICIOUS_PATH_KEYWORDS = {
    "admin", "wp-login", "wp-admin", ".env", "config", "passwd",
    "shadow", "etc/", "proc/", "cmd.exe", "phpinfo", "shell",
    "sqlmap", "nikto", "upload", "backup", "database", "phpmyadmin",
    "actuator", "console", ".git", ".DS_Store", ".htaccess",
}


@dataclass
class AnomalyResult:
    """Result of anomaly prediction for a single log entry."""
    log_entry: LogEntry
    is_anomaly: bool
    anomaly_score: float          # -1.0 (most anomalous) to 1.0 (most normal)
    features: Dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sha256_of_file(path: Path) -> str:
    """Return the lowercase hex SHA-256 digest of *path*."""
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(65536), b""):
            h.update(block)
    return h.hexdigest()


# ---------------------------------------------------------------------------
# Feature engineering
# ---------------------------------------------------------------------------

def extract_features(entry: LogEntry) -> Dict[str, float]:
    """
    Extract a fixed-length numeric feature vector from a LogEntry.

    Returns:
        Dict mapping feature name → float value.
    """
    # status_code
    status_code = float(entry.status_code or 0)

    # bytes_sent
    bytes_sent = float(entry.bytes_sent or 0)

    # is_post
    is_post = 1.0 if (entry.method or "").upper() == "POST" else 0.0

    # is_error
    is_error = 1.0 if status_code >= 400 else 0.0

    # path_depth
    path = entry.path or entry.message or ""
    path_depth = float(path.count("/"))

    # has_suspicious_path
    path_lower = path.lower()
    has_suspicious = 1.0 if any(kw in path_lower for kw in _SUSPICIOUS_PATH_KEYWORDS) else 0.0

    # hour_of_day
    if entry.timestamp:
        hour_of_day = float(entry.timestamp.hour)
    else:
        hour_of_day = 12.0  # neutral default

    # bytes_log: log-scale bytes to reduce outlier effect
    bytes_log = float(np.log1p(bytes_sent))

    return {
        "status_code":         status_code,
        "bytes_sent":          bytes_sent,
        "bytes_log":           bytes_log,
        "is_post":             is_post,
        "is_error":            is_error,
        "path_depth":          path_depth,
        "has_suspicious_path": has_suspicious,
        "hour_of_day":         hour_of_day,
        "request_rate_1min":   0.0,  # Filled in by _add_request_rates()
    }


def _add_request_rates(features_list: List[Dict[str, float]], entries: List[LogEntry]) -> None:
    """
    Compute per-IP request frequency in this batch and store it as
    `request_rate_1min` in each feature dict (in-place).
    """
    from collections import Counter
    ip_counts: Counter = Counter(e.source_ip or "unknown" for e in entries)
    max_count = max(ip_counts.values(), default=1)
    for feat, entry in zip(features_list, entries):
        ip = entry.source_ip or "unknown"
        # Normalise to [0, 1]
        feat["request_rate_1min"] = ip_counts[ip] / max_count


def _features_to_matrix(features_list: List[Dict[str, float]]) -> np.ndarray:
    """Convert a list of feature dicts to a 2-D numpy matrix."""
    keys = [
        "status_code", "bytes_sent", "bytes_log", "is_post", "is_error",
        "path_depth", "has_suspicious_path", "hour_of_day", "request_rate_1min",
    ]
    return np.array([[f[k] for k in keys] for f in features_list], dtype=float)


# ---------------------------------------------------------------------------
# IsolationForest wrapper
# ---------------------------------------------------------------------------

class AnomalyDetector:
    """Singleton wrapper around sklearn IsolationForest."""

    def __init__(self) -> None:
        settings = get_settings()
        self._model: Optional[IsolationForest] = None
        self._contamination = settings.anomaly_contamination
        self._model_path = Path(settings.anomaly_model_path)
        self._digest_path = self._model_path.with_suffix(".sha256")
        self._lock = threading.Lock()

    def fit(self, log_entries: List[LogEntry]) -> None:
        """
        Fit the Isolation Forest on *log_entries* and persist the model.

        Args:
            log_entries: Training log entries (ideally a large representative set).
        """
        if not log_entries:
            raise ValueError("Cannot fit on an empty list of log entries.")

        features_list = [extract_features(e) for e in log_entries]
        _add_request_rates(features_list, log_entries)
        X = _features_to_matrix(features_list)

        logger.info(
            f"Fitting IsolationForest on {len(log_entries)} entries "
            f"(contamination={self._contamination})…"
        )
        self._model = IsolationForest(
            n_estimators=100,
            contamination=self._contamination,
            random_state=42,
            n_jobs=-1,
        )
        self._model.fit(X)
        self._save()
        logger.info("IsolationForest fitted and saved.")

    def predict(self, log_entries: List[LogEntry]) -> List[AnomalyResult]:
        """
        Predict anomaly labels for *log_entries*.

        Args:
            log_entries: Entries to classify.

        Returns:
            List of AnomalyResult (one per entry).
        """
        if self._model is None:
            raise RuntimeError(
                "Model is not fitted. Call fit() or load_or_fit() first."
            )
        if not log_entries:
            return []

        features_list = [extract_features(e) for e in log_entries]
        _add_request_rates(features_list, log_entries)
        X = _features_to_matrix(features_list)

        raw_labels = self._model.predict(X)           # -1 or +1
        raw_scores = self._model.score_samples(X)     # negative; more negative = more anomalous

        # Normalise scores to [-1, 1]: -1 = anomaly, +1 = normal
        # score_samples range is roughly (-0.5, 0); we remap to [-1, 1]
        min_s, max_s = raw_scores.min(), raw_scores.max()
        if max_s == min_s:
            norm_scores = np.zeros_like(raw_scores)
        else:
            norm_scores = 2.0 * (raw_scores - min_s) / (max_s - min_s) - 1.0

        results: List[AnomalyResult] = []
        for entry, label, score, feat in zip(
            log_entries, raw_labels, norm_scores, features_list
        ):
            is_anomaly = bool(label == -1)
            results.append(
                AnomalyResult(
                    log_entry=entry,
                    is_anomaly=is_anomaly,
                    anomaly_score=float(score),
                    features=feat,
                )
            )

        anomaly_count = sum(1 for r in results if r.is_anomaly)
        logger.info(
            f"Predicted {len(results)} entries: "
            f"{anomaly_count} anomalies ({anomaly_count / len(results) * 100:.1f}%)"
        )
        return results

    def load_or_fit(self, log_entries: List[LogEntry]) -> None:
        """
        Load a persisted model if available; otherwise fit a new one.

        Args:
            log_entries: Entries to use for fitting if no saved model exists.
        """
        if self._model_path.exists():
            self._load()
        else:
            self.fit(log_entries)

    def _save(self) -> None:
        """Persist the model with joblib and write a SHA-256 digest for integrity checks."""
        self._model_path.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(self._model, self._model_path)
        digest = _sha256_of_file(self._model_path)
        self._digest_path.write_text(digest, encoding="utf-8")
        logger.debug(f"Model saved to {self._model_path} (sha256={digest[:12]}…)")

    def _load(self) -> None:
        """Load the model, verifying SHA-256 integrity before deserializing."""
        if self._digest_path.exists():
            expected = self._digest_path.read_text(encoding="utf-8").strip()
            actual = _sha256_of_file(self._model_path)
            if actual != expected:
                raise RuntimeError(
                    f"Model integrity check FAILED for {self._model_path}. "
                    f"Expected sha256={expected[:12]}…, got {actual[:12]}…. "
                    "Delete the model file and re-ingest to rebuild it."
                )
        else:
            logger.warning(
                f"No .sha256 digest found for {self._model_path} — "
                "skipping integrity check (legacy model file)."
            )
        self._model = joblib.load(self._model_path)
        logger.info(f"Loaded IsolationForest from {self._model_path}")

    @property
    def is_fitted(self) -> bool:
        return self._model is not None


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_detector: Optional[AnomalyDetector] = None
_detector_lock = threading.Lock()


def get_detector() -> AnomalyDetector:
    """Return the module-level AnomalyDetector singleton (thread-safe)."""
    global _detector
    if _detector is None:
        with _detector_lock:
            if _detector is None:  # double-checked locking
                _detector = AnomalyDetector()
    return _detector
