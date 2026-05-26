"""
Regex parsers for three common log formats:

  1. Apache / Nginx Combined Log Format
  2. Syslog (RFC 3164-ish)
  3. Generic key=value format

Each parser returns a normalised dict:
  {
      "timestamp":  str | None,
      "source_ip":  str | None,
      "log_level":  str | None,
      "message":    str,
      "raw":        str,
      "format_type": str,
      # format-specific extras kept as top-level keys
  }
"""

import re
from typing import Optional

# ---------------------------------------------------------------------------
# 1. Apache / Nginx Combined Log Format
#    127.0.0.1 - frank [10/Oct/2000:13:55:36 -0700] "GET /index.html HTTP/1.1" 200 2326 "-" "Mozilla/5.0"
# ---------------------------------------------------------------------------
_APACHE_PATTERN = re.compile(
    r'(?P<source_ip>\S+)'           # client IP
    r'\s+\S+'                       # ident (usually -)
    r'\s+\S+'                       # auth user (usually -)
    r'\s+\[(?P<timestamp>[^\]]+)\]' # [timestamp]
    r'\s+"(?P<method>\S+)'          # HTTP method
    r'\s+(?P<path>\S+)'             # URL path
    r'\s+(?P<protocol>[^"]+)"'      # protocol
    r'\s+(?P<status_code>\d{3})'    # HTTP status
    r'\s+(?P<bytes_sent>\S+)'       # bytes (may be -)
    r'(?:\s+"(?P<referer>[^"]*)")?'  # optional referer
    r'(?:\s+"(?P<user_agent>[^"]*)")?'  # optional user-agent
)

# ---------------------------------------------------------------------------
# 2. Syslog
#    May 26 14:30:01 myhost sshd[1234]: Failed password for root from 1.2.3.4
# ---------------------------------------------------------------------------
_SYSLOG_PATTERN = re.compile(
    r'(?P<timestamp>\w{3}\s+\d{1,2}\s+\d{2}:\d{2}:\d{2})'  # Month Day HH:MM:SS
    r'\s+(?P<hostname>\S+)'                                   # hostname
    r'\s+(?P<process>\S+?)(?:\[(?P<pid>\d+)\])?:'            # process[pid]:
    r'\s*(?P<message>.*)'                                     # message body
)

# ---------------------------------------------------------------------------
# 3. Generic key=value
#    2024-01-15T10:30:00Z INFO src_ip=192.168.1.1 status=200 path=/api/health
# ---------------------------------------------------------------------------
_KV_PATTERN = re.compile(
    r'(?P<timestamp>\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:[.,]\d+)?(?:Z|[+-]\d{2}:?\d{2})?)'
    r'(?:\s+(?P<log_level>DEBUG|INFO|WARNING|WARN|ERROR|CRITICAL|NOTICE|TRACE))?'
    r'(?P<kv_pairs>.*)'
)
_KV_PAIR = re.compile(r'(\w+)=([^\s"]+|"[^"]*")')


def _safe_int(value: Optional[str], default: int = 0) -> int:
    """Convert a string to int, returning *default* on failure."""
    try:
        return int(value) if value and value != "-" else default
    except (ValueError, TypeError):
        return default


def parse_apache(line: str) -> Optional[dict]:
    """
    Parse an Apache / Nginx Combined Log Format line.

    Returns a normalised dict or *None* if the line does not match.
    """
    m = _APACHE_PATTERN.match(line.strip())
    if not m:
        return None

    d = m.groupdict()
    return {
        "timestamp": d.get("timestamp"),
        "source_ip": d.get("source_ip"),
        "log_level": _http_status_to_level(d.get("status_code", "0")),
        "message": (
            f'{d.get("method", "-")} {d.get("path", "-")} '
            f'-> {d.get("status_code", "-")} '
            f'({d.get("bytes_sent", "0")} bytes)'
        ),
        "raw": line,
        "format_type": "apache",
        # extra fields
        "method": d.get("method"),
        "path": d.get("path"),
        "status_code": _safe_int(d.get("status_code")),
        "bytes_sent": _safe_int(d.get("bytes_sent")),
        "user_agent": d.get("user_agent"),
        "referer": d.get("referer"),
    }


def parse_syslog(line: str) -> Optional[dict]:
    """
    Parse a Syslog-format line.

    Returns a normalised dict or *None* if the line does not match.
    """
    m = _SYSLOG_PATTERN.match(line.strip())
    if not m:
        return None

    d = m.groupdict()
    msg = d.get("message", "")
    # Try to extract an IP address from the message for source_ip
    ip_match = re.search(r'\b(\d{1,3}(?:\.\d{1,3}){3})\b', msg)

    return {
        "timestamp": d.get("timestamp"),
        "source_ip": ip_match.group(1) if ip_match else None,
        "log_level": _syslog_message_to_level(msg),
        "message": msg,
        "raw": line,
        "format_type": "syslog",
        # extra fields
        "hostname": d.get("hostname"),
        "process": d.get("process"),
        "pid": _safe_int(d.get("pid")),
    }


def parse_kv(line: str) -> Optional[dict]:
    """
    Parse a generic timestamp + optional level + key=value format.

    Returns a normalised dict or *None* if no timestamp is detected.
    """
    m = _KV_PATTERN.match(line.strip())
    if not m:
        return None

    d = m.groupdict()
    kv_pairs = dict(
        (k, v.strip('"'))
        for k, v in _KV_PAIR.findall(d.get("kv_pairs", ""))
    )

    source_ip = kv_pairs.get("src_ip") or kv_pairs.get("source_ip") or kv_pairs.get("ip")

    return {
        "timestamp": d.get("timestamp"),
        "source_ip": source_ip,
        "log_level": d.get("log_level") or kv_pairs.get("level") or kv_pairs.get("log_level"),
        "message": d.get("kv_pairs", "").strip(),
        "raw": line,
        "format_type": "kv",
        # expose all parsed k/v pairs at top level for convenience
        **kv_pairs,
    }


def auto_detect_and_parse(line: str) -> Optional[dict]:
    """
    Try each parser in order; return the first successful result.
    Returns *None* if no parser matched.
    """
    line = line.strip()
    if not line or line.startswith("#"):
        return None

    for parser in (parse_apache, parse_syslog, parse_kv):
        result = parser(line)
        if result is not None:
            return result

    # Fallback: treat the whole line as a raw message
    return {
        "timestamp": None,
        "source_ip": None,
        "log_level": "UNKNOWN",
        "message": line,
        "raw": line,
        "format_type": "unknown",
    }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _http_status_to_level(status: Optional[str]) -> str:
    """Map HTTP status code to a log level string."""
    code = _safe_int(status)
    if code >= 500:
        return "ERROR"
    if code >= 400:
        return "WARNING"
    if code >= 300:
        return "INFO"
    return "INFO"


def _syslog_message_to_level(message: str) -> str:
    """Infer a log level from syslog message keywords."""
    msg_lower = message.lower()
    if any(k in msg_lower for k in ("error", "fail", "critical", "emerg", "alert", "crit")):
        return "ERROR"
    if any(k in msg_lower for k in ("warn", "invalid", "denied", "refused")):
        return "WARNING"
    return "INFO"
