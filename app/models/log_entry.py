"""
Pydantic models for normalised log entries.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

# Supported Apache timestamp formats
_APACHE_TS_FMT = "%d/%b/%Y:%H:%M:%S %z"
# Syslog timestamp (no year, so we inject the current year)
_SYSLOG_TS_FMT = "%b %d %H:%M:%S"
# ISO / generic
_ISO_TS_FMTS = [
    "%Y-%m-%dT%H:%M:%SZ",
    "%Y-%m-%dT%H:%M:%S%z",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%dT%H:%M:%S.%f%z",
    "%Y-%m-%dT%H:%M:%S.%fZ",
]

_IP_RE = re.compile(
    r"^(\d{1,3}\.){3}\d{1,3}$|"        # IPv4
    r"^([0-9a-fA-F]{0,4}:){2,7}[0-9a-fA-F]{0,4}$"  # IPv6 (simplified)
)


def _parse_timestamp(raw: Optional[str]) -> Optional[datetime]:
    """Try a series of timestamp formats; return *None* if all fail."""
    if not raw:
        return None

    raw = raw.strip()

    for fmt in _ISO_TS_FMTS:
        try:
            return datetime.strptime(raw, fmt)
        except ValueError:
            pass

    # Apache combined log format
    try:
        return datetime.strptime(raw, _APACHE_TS_FMT)
    except ValueError:
        pass

    # Syslog (inject current year)
    try:
        dt = datetime.strptime(raw, _SYSLOG_TS_FMT)
        return dt.replace(year=datetime.now(tz=timezone.utc).year)
    except ValueError:
        pass

    return None


class LogEntry(BaseModel):
    """Normalised representation of a single log line."""

    # Core normalised fields
    timestamp_raw: Optional[str] = None
    timestamp: Optional[datetime] = None
    source_ip: Optional[str] = None
    log_level: Optional[str] = "UNKNOWN"
    message: str = ""
    raw: str = ""
    format_type: str = "unknown"

    # HTTP-specific (Apache/Nginx)
    method: Optional[str] = None
    path: Optional[str] = None
    status_code: Optional[int] = None
    bytes_sent: Optional[int] = None
    user_agent: Optional[str] = None
    referer: Optional[str] = None

    # Syslog-specific
    hostname: Optional[str] = None
    process: Optional[str] = None
    pid: Optional[int] = None

    # Extra k/v pairs captured from generic format
    extra: dict[str, Any] = Field(default_factory=dict)

    # Anomaly metadata (set after anomaly detection pass)
    is_anomaly: bool = False
    anomaly_score: float = 0.0

    @field_validator("source_ip", mode="before")
    @classmethod
    def validate_ip(cls, v: Optional[str]) -> Optional[str]:
        """Accept valid IPv4/IPv6 addresses; return *None* for invalid values."""
        if v is None:
            return None
        v = str(v).strip()
        if not v or v == "-":
            return None
        # Accept if it looks like a valid IP
        if _IP_RE.match(v):
            return v
        # Some log lines put partial IPs or hostnames — keep them as-is but don't validate strictly
        return v

    @field_validator("log_level", mode="before")
    @classmethod
    def normalise_level(cls, v: Optional[str]) -> str:
        """Upper-case the log level; default to UNKNOWN."""
        if not v:
            return "UNKNOWN"
        return str(v).upper()

    @model_validator(mode="before")
    @classmethod
    def parse_timestamp_field(cls, data: dict) -> dict:
        """
        Parse *timestamp_raw* → *timestamp* (datetime) if not already set.
        """
        raw_ts = data.get("timestamp") or data.get("timestamp_raw")
        if raw_ts and not isinstance(raw_ts, datetime):
            data["timestamp_raw"] = raw_ts
            data["timestamp"] = _parse_timestamp(str(raw_ts))
        return data

    # ------------------------------------------------------------------
    # Convenience
    # ------------------------------------------------------------------

    def to_chunk_text(self) -> str:
        """
        Return a human-readable string suitable for embedding.
        Includes all meaningful fields in a flat representation.
        """
        parts: list[str] = []

        if self.timestamp:
            parts.append(f"[{self.timestamp.isoformat()}]")
        elif self.timestamp_raw:
            parts.append(f"[{self.timestamp_raw}]")

        if self.source_ip:
            parts.append(f"IP:{self.source_ip}")

        if self.log_level and self.log_level != "UNKNOWN":
            parts.append(f"LEVEL:{self.log_level}")

        if self.format_type == "apache":
            parts.append(
                f"HTTP {self.method or '-'} {self.path or '-'} "
                f"STATUS:{self.status_code or '-'} "
                f"BYTES:{self.bytes_sent or 0}"
            )
            if self.user_agent:
                parts.append(f"UA:{self.user_agent[:80]}")
        else:
            if self.message:
                parts.append(self.message[:500])

        if self.is_anomaly:
            parts.append(f"[ANOMALY score={self.anomaly_score:.3f}]")

        return " | ".join(parts) if parts else self.raw[:500]

    @classmethod
    def from_parsed_dict(cls, data: dict) -> "LogEntry":
        """
        Build a LogEntry from the dict returned by a log_parser function.
        Unknown keys are folded into *extra*.
        """
        known_keys = cls.model_fields.keys()
        extra: dict[str, Any] = {}
        clean: dict[str, Any] = {}

        for k, v in data.items():
            if k in known_keys:
                clean[k] = v
            else:
                extra[k] = v

        clean["extra"] = extra
        return cls(**clean)
