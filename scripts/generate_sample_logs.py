"""
Generate 500 synthetic Apache Combined Log Format entries.

Distribution:
  - 85% normal traffic  (GET/POST, status 200/304, common paths)
  - 10% suspicious      (repeated 401/403, unusual paths like /admin, /wp-login.php)
  -  5% anomalous       (SQL injection, path traversal, enormous byte counts)

Output: data/raw_logs/sample_access.log
"""

from __future__ import annotations

import random
import sys
from datetime import datetime, timedelta
from pathlib import Path

# ── Make sure project root is on sys.path when run directly ─────────────────
sys.path.insert(0, str(Path(__file__).parent.parent))

OUTPUT_FILE = Path("data/raw_logs/sample_access.log")
TOTAL_LINES = 500

# ── Data pools ───────────────────────────────────────────────────────────────

NORMAL_IPS = [f"192.168.1.{i}" for i in range(10, 60)]
SUSPICIOUS_IPS = [f"10.0.0.{i}" for i in range(1, 20)] + [
    "185.220.101.55", "45.33.32.156", "198.199.91.32", "104.21.14.178",
]
ANOMALOUS_IPS = ["1.2.3.4", "5.6.7.8", "255.255.255.0", "0.0.0.0"]

NORMAL_PATHS = [
    "/", "/index.html", "/about", "/contact", "/login", "/dashboard",
    "/api/health", "/api/status", "/api/v1/users", "/api/v1/products",
    "/static/css/main.css", "/static/js/app.js", "/favicon.ico",
    "/images/logo.png", "/search?q=test", "/profile", "/settings",
]
SUSPICIOUS_PATHS = [
    "/admin", "/admin/login", "/wp-login.php", "/wp-admin/",
    "/.env", "/.git/config", "/config.php", "/phpinfo.php",
    "/server-status", "/actuator/env", "/actuator/health",
    "/console", "/.DS_Store", "/backup.zip", "/database.sql",
]
ANOMALOUS_PATHS = [
    "/index.php?id=1' OR '1'='1",
    "/search?q=<script>alert(1)</script>",
    "/../../../../etc/passwd",
    "/../../windows/system32/cmd.exe",
    "/admin?username=admin'--",
    "/login?user=root&pass='; DROP TABLE users;--",
    "/api/v1/user?id=../../../etc/shadow",
    "/%2e%2e%2f%2e%2e%2fetc%2fpasswd",
]

METHODS_NORMAL = ["GET"] * 7 + ["POST"] * 3
METHODS_SUSPICIOUS = ["GET"] * 5 + ["POST"] * 4 + ["HEAD"]
METHODS_ANOMALOUS = ["GET"] * 4 + ["POST"] * 4 + ["PUT", "DELETE"]

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64; rv:109.0) Gecko/20100101 Firefox/109.0",
    "curl/7.88.1",
    "python-requests/2.31.0",
    "Go-http-client/1.1",
]
MALICIOUS_UAS = [
    "sqlmap/1.7.8#stable (https://sqlmap.org)",
    "Nikto/2.1.6",
    "masscan/1.3.2",
    "zgrab/0.x",
    "-",
]

# ── Line builder ─────────────────────────────────────────────────────────────

def _apache_line(
    ip: str,
    path: str,
    method: str,
    status: int,
    bytes_sent: int,
    ua: str,
    ts: datetime,
) -> str:
    timestamp_str = ts.strftime("%d/%b/%Y:%H:%M:%S +0000")
    return (
        f'{ip} - - [{timestamp_str}] '
        f'"{method} {path} HTTP/1.1" '
        f'{status} {bytes_sent} '
        f'"-" "{ua}"'
    )


def _random_ts(base: datetime, jitter_seconds: int = 3600) -> datetime:
    return base + timedelta(seconds=random.randint(0, jitter_seconds))


# ── Main generation logic ─────────────────────────────────────────────────────

def generate_logs(n: int = TOTAL_LINES) -> list[str]:
    base_time = datetime(2024, 6, 1, 0, 0, 0)
    lines: list[str] = []

    n_normal     = int(n * 0.85)
    n_suspicious = int(n * 0.10)
    n_anomalous  = n - n_normal - n_suspicious

    # ── Normal traffic ──────────────────────────────────────────────────────
    for i in range(n_normal):
        ts      = _random_ts(base_time, jitter_seconds=86400)
        ip      = random.choice(NORMAL_IPS)
        path    = random.choice(NORMAL_PATHS)
        method  = random.choice(METHODS_NORMAL)
        status  = random.choices([200, 200, 200, 304, 301, 302], weights=[60, 60, 60, 10, 5, 5])[0]
        bsent   = random.randint(200, 50_000)
        ua      = random.choice(USER_AGENTS)
        lines.append(_apache_line(ip, path, method, status, bsent, ua, ts))

    # ── Suspicious traffic ──────────────────────────────────────────────────
    for i in range(n_suspicious):
        ts      = _random_ts(base_time, jitter_seconds=86400)
        ip      = random.choice(SUSPICIOUS_IPS)
        path    = random.choice(SUSPICIOUS_PATHS)
        method  = random.choice(METHODS_SUSPICIOUS)
        status  = random.choices([401, 403, 404, 200], weights=[40, 35, 15, 10])[0]
        bsent   = random.randint(100, 5_000)
        ua      = random.choice(USER_AGENTS + MALICIOUS_UAS)
        lines.append(_apache_line(ip, path, method, status, bsent, ua, ts))

    # ── Anomalous traffic ───────────────────────────────────────────────────
    for i in range(n_anomalous):
        ts      = _random_ts(base_time, jitter_seconds=86400)
        ip      = random.choice(ANOMALOUS_IPS + SUSPICIOUS_IPS)
        path    = random.choice(ANOMALOUS_PATHS)
        method  = random.choice(METHODS_ANOMALOUS)
        status  = random.choices([200, 400, 500, 403], weights=[30, 30, 20, 20])[0]
        # Anomalous: either tiny (0 bytes) or enormous
        bsent   = random.choice([0, random.randint(5_000_000, 50_000_000)])
        ua      = random.choice(MALICIOUS_UAS)
        lines.append(_apache_line(ip, path, method, status, bsent, ua, ts))

    # Shuffle so categories are interleaved
    random.shuffle(lines)
    return lines


def main() -> None:
    random.seed(42)  # reproducible output
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)

    lines = generate_logs(TOTAL_LINES)

    with OUTPUT_FILE.open("w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")

    print(f"[OK] Generated {len(lines)} log lines -> {OUTPUT_FILE}")

    # Quick sanity stats
    statuses = {}
    for line in lines:
        parts = line.split('"')
        if len(parts) >= 3:
            code = parts[2].strip().split()[0]
            statuses[code] = statuses.get(code, 0) + 1
    print("  Status code breakdown:")
    for code, count in sorted(statuses.items()):
        print(f"    {code}: {count}")


if __name__ == "__main__":
    main()
