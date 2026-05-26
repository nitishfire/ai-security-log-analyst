"""
In-memory sliding-window rate limiter implemented as FastAPI dependencies.

Usage in a route:
    from fastapi import Depends
    from app.core.rate_limit import ingest_limiter

    @router.post("", dependencies=[Depends(ingest_limiter)])
    async def my_route(...):
        ...

Limits are per source IP.  The limiter uses a thread-safe sliding-window
counter that automatically evicts stale entries to bound memory usage.
"""

from __future__ import annotations

import threading
import time
from typing import Dict, List

from fastapi import HTTPException, Request, status


class _SlidingWindowLimiter:
    """
    Per-IP sliding-window rate limiter.

    Raises HTTP 429 when a single IP exceeds *max_requests* within the
    last *window_seconds*.  Stale entries are pruned periodically so
    memory is bounded.

    Thread-safe: a single lock serialises all mutations.
    """

    def __init__(self, max_requests: int, window_seconds: float) -> None:
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._windows: Dict[str, List[float]] = {}
        self._lock = threading.Lock()
        self._last_cleanup: float = time.monotonic()

    # ------------------------------------------------------------------
    # FastAPI dependency — callable interface
    # ------------------------------------------------------------------

    def __call__(self, request: Request) -> None:
        """Raise HTTP 429 if the caller's IP exceeds the rate limit."""
        ip: str = (
            (request.client.host if request.client else None) or "unknown"
        )
        now = time.monotonic()
        cutoff = now - self.window_seconds

        with self._lock:
            self._maybe_cleanup(now)

            # Prune timestamps outside the current window for this IP
            window = [t for t in self._windows.get(ip, []) if t > cutoff]

            if len(window) >= self.max_requests:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail=(
                        f"Rate limit exceeded: {self.max_requests} requests "
                        f"per {int(self.window_seconds)} s."
                    ),
                    headers={"Retry-After": str(int(self.window_seconds))},
                )

            window.append(now)
            self._windows[ip] = window

    def _maybe_cleanup(self, now: float) -> None:
        """Evict fully-expired IP windows (called while holding the lock)."""
        if now - self._last_cleanup < self.window_seconds:
            return
        cutoff = now - self.window_seconds
        self._windows = {
            ip: ts
            for ip, ts in self._windows.items()
            if ts and ts[-1] > cutoff
        }
        self._last_cleanup = now


# ---------------------------------------------------------------------------
# Pre-configured instances — import and use directly as dependencies
# ---------------------------------------------------------------------------

#: Heavy CPU/IO endpoint — allow 10 ingests per minute per IP
ingest_limiter = _SlidingWindowLimiter(max_requests=10, window_seconds=60)

#: LLM-backed query — allow 20 queries per minute per IP
query_limiter = _SlidingWindowLimiter(max_requests=20, window_seconds=60)

#: Read-only endpoints — allow 120 requests per minute per IP
read_limiter = _SlidingWindowLimiter(max_requests=120, window_seconds=60)
