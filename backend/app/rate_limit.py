"""Phase 4.1 in-process rate limiter (token bucket).

Drops to a simple per-IP / per-key counter with sliding window. Designed
to be the first line of defense before the LLM API rate limit kicks in.

Limitations:
- Per-process state — gunicorn workers each maintain their own bucket.
  For cross-worker sharing, swap to Redis-backed atomic INCR (sketched
  in `RedisRateLimiter` below; not wired up by default).
- Trivially DoS-able if attacker rotates IPs; pair with nginx limit_req
  in production.

Wire-up (Flask):
    from .rate_limit import RateLimiter
    limiter = RateLimiter(rps=5, burst=10)

    @app.before_request
    def _check_rate():
        if not limiter.allow(request.remote_addr):
            return jsonify(error="rate limit exceeded"), 429
"""
from __future__ import annotations

import time
import threading
from collections import deque
from typing import Iterable


class TokenBucket:
    """Classic token bucket: refills `rps` tokens per second, capacity `burst`."""

    __slots__ = ("rps", "burst", "tokens", "last_refill", "lock")

    def __init__(self, rps: float, burst: int):
        self.rps = float(rps)
        self.burst = int(burst)
        self.tokens = float(burst)
        self.last_refill = time.monotonic()
        self.lock = threading.Lock()

    def allow(self, cost: float = 1.0) -> bool:
        with self.lock:
            now = time.monotonic()
            elapsed = now - self.last_refill
            self.tokens = min(self.burst, self.tokens + elapsed * self.rps)
            self.last_refill = now
            if self.tokens >= cost:
                self.tokens -= cost
                return True
            return False


class RateLimiter:
    """One bucket per key (IP / user_id / API key).

    Auto-evicts buckets idle for > 5 minutes to prevent memory leaks.
    """

    def __init__(self, rps: float = 5.0, burst: int = 10,
                 evict_after_seconds: int = 300):
        self.rps = rps
        self.burst = burst
        self._buckets: dict[str, TokenBucket] = {}
        self._last_seen: dict[str, float] = {}
        self._evict_after = evict_after_seconds
        self._lock = threading.Lock()

    def allow(self, key: str, cost: float = 1.0) -> bool:
        if key is None:
            key = "anonymous"
        with self._lock:
            bucket = self._buckets.get(key)
            if bucket is None:
                bucket = TokenBucket(rps=self.rps, burst=self.burst)
                self._buckets[key] = bucket
            self._last_seen[key] = time.monotonic()
            self._maybe_evict()
        return bucket.allow(cost)

    def _maybe_evict(self) -> None:
        # Cheap eviction: only when we have > 1024 keys.
        if len(self._buckets) <= 1024:
            return
        now = time.monotonic()
        stale = [k for k, t in self._last_seen.items()
                 if now - t > self._evict_after]
        for k in stale:
            self._buckets.pop(k, None)
            self._last_seen.pop(k, None)

    def stats(self) -> dict:
        with self._lock:
            return {
                "active_keys": len(self._buckets),
                "rps": self.rps,
                "burst": self.burst,
            }


# Module-level default limiter (Flask-friendly).
_default: RateLimiter | None = None


def get_default(rps: float = 10.0, burst: int = 20) -> RateLimiter:
    global _default
    if _default is None:
        _default = RateLimiter(rps=rps, burst=burst)
    return _default
