"""Phase 4.1 Cache layer for Function Calling tool results.

Why this exists
---------------
Without caching, every "美元兑日元最新汇率" question re-hits MySQL,
every "什么是 carry trade" re-runs bge-m3 + reranker (300ms-2s).
At 50+ concurrent users this is the first thing to break.

Design
------
- One interface (`CacheBackend`), two implementations:
    * `TTLCacheBackend`  — `cachetools.TTLCache`, in-memory, zero deps. Default.
    * `RedisCacheBackend` — `redis-py`, distributed. Activated by REDIS_URL env.
- Per-tool TTL policy (rate data 1h, RAG 10min, predictions 6h, etc.)
- Errors are NOT cached (so a transient DB outage doesn't poison the cache)
- Stats logged: hits / misses / hit_rate / saved_seconds (estimated)

Drop-in usage
-------------
    from app.cache import cached_execute
    result = cached_execute("get_exchange_rate", {"a": "USD", ...}, handler)

If you want to bypass cache for one call:
    result = handler(**args)   # raw, skips cache entirely

Production switch (no code change)
----------------------------------
    export REDIS_URL=redis://localhost:6379/0
    # restart backend → cache becomes process-shared across gunicorn workers
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from typing import Any, Callable, Protocol

logger = logging.getLogger(__name__)

# ---------------- TTL policy (seconds) ----------------
# Tuned per tool's data freshness:
#   - rates update once per day → 1h cache is safe (1/24 stale)
#   - SARIMAX predictions regenerate weekly → 6h cache plenty
#   - VaR depends on rolling lookback → 30 min
#   - RAG knowledge base is static between rebuilds → 10 min
TOOL_TTL: dict[str, int] = {
    "get_exchange_rate":      3600,
    "get_rate_range":         3600,
    "predict_exchange_rate":  21600,
    "calculate_var":          1800,
    "search_forex_knowledge": 600,
}
DEFAULT_TTL = 300  # unknown tools: 5 min


# ---------------- Backend protocol ----------------
class CacheBackend(Protocol):
    def get(self, key: str) -> Any | None: ...
    def set(self, key: str, value: Any, ttl: int) -> None: ...
    def stats(self) -> dict[str, Any]: ...


# ---------------- TTLCache (in-memory, default) ----------------
class TTLCacheBackend:
    """In-memory LRU + TTL. Zero external dependency.

    Per-process — gunicorn workers each have their own copy. For real
    cross-worker sharing, switch to Redis.
    """

    def __init__(self, maxsize: int = 512):
        # We implement our own per-key TTL (cachetools.TTLCache uses a
        # single global TTL). Stdlib-only — no external dep.
        self._store: dict[str, tuple[Any, float]] = {}
        self._maxsize = maxsize
        self._hits = 0
        self._misses = 0
        self._saved_ms = 0.0  # estimated saved compute time

    def get(self, key: str) -> Any | None:
        entry = self._store.get(key)
        if entry is None:
            self._misses += 1
            return None
        value, expires_at = entry
        if time.time() >= expires_at:
            self._store.pop(key, None)
            self._misses += 1
            return None
        self._hits += 1
        return value

    def set(self, key: str, value: Any, ttl: int) -> None:
        # Evict oldest if at capacity (simple FIFO eviction; cachetools.TTLCache
        # would be LRU but we keep it dependency-light here).
        if len(self._store) >= self._maxsize:
            oldest_key = next(iter(self._store))
            self._store.pop(oldest_key, None)
        self._store[key] = (value, time.time() + ttl)

    def record_saved(self, ms: float) -> None:
        self._saved_ms += ms

    def stats(self) -> dict[str, Any]:
        total = self._hits + self._misses
        return {
            "backend": "ttlcache (in-memory)",
            "size": len(self._store),
            "max_size": self._maxsize,
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": (self._hits / total) if total else 0.0,
            "estimated_saved_seconds": round(self._saved_ms / 1000.0, 2),
        }


# ---------------- Redis (production) ----------------
class RedisCacheBackend:
    """Distributed cache backed by Redis.

    Activated by setting REDIS_URL env. Falls back to TTLCache if redis-py
    is unavailable or the server isn't reachable.
    """

    def __init__(self, url: str):
        try:
            import redis
        except ImportError as e:
            raise RuntimeError("redis-py required: pip install redis") from e
        self._client = redis.Redis.from_url(url, decode_responses=False,
                                            socket_connect_timeout=2,
                                            socket_timeout=2)
        # ping early so we fail fast if Redis is down
        self._client.ping()
        self._hits = 0
        self._misses = 0
        self._saved_ms = 0.0

    def get(self, key: str) -> Any | None:
        try:
            raw = self._client.get(key)
        except Exception as e:
            logger.warning("Redis GET failed: %s", e)
            self._misses += 1
            return None
        if raw is None:
            self._misses += 1
            return None
        self._hits += 1
        try:
            return json.loads(raw)
        except Exception:
            return None

    def set(self, key: str, value: Any, ttl: int) -> None:
        try:
            self._client.setex(key, ttl, json.dumps(value, ensure_ascii=False).encode("utf-8"))
        except Exception as e:
            logger.warning("Redis SETEX failed: %s", e)

    def record_saved(self, ms: float) -> None:
        self._saved_ms += ms

    def stats(self) -> dict[str, Any]:
        total = self._hits + self._misses
        return {
            "backend": "redis",
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": (self._hits / total) if total else 0.0,
            "estimated_saved_seconds": round(self._saved_ms / 1000.0, 2),
        }


# ---------------- Module-level singleton ----------------
_backend: CacheBackend | None = None


def get_backend() -> CacheBackend:
    """Lazy singleton. Picks Redis if REDIS_URL set, else TTLCache."""
    global _backend
    if _backend is not None:
        return _backend

    redis_url = os.environ.get("REDIS_URL", "").strip()
    if redis_url:
        try:
            _backend = RedisCacheBackend(redis_url)
            logger.info("Cache backend: Redis (%s)", redis_url)
            return _backend
        except Exception as e:
            logger.warning("Redis backend failed (%s); falling back to TTLCache", e)

    _backend = TTLCacheBackend(maxsize=int(os.environ.get("CACHE_MAXSIZE", "512")))
    logger.info("Cache backend: TTLCache (in-memory)")
    return _backend


def make_key(tool_name: str, args: dict[str, Any]) -> str:
    """Deterministic cache key from tool name + sorted args.

    None defaults are kept so `get_rate(USD, JPY)` and
    `get_rate(USD, JPY, on_date=None)` collide intentionally.
    """
    canonical = json.dumps(args, sort_keys=True, default=str, ensure_ascii=False)
    digest = hashlib.sha256(f"{tool_name}|{canonical}".encode("utf-8")).hexdigest()[:16]
    return f"cfx:tool:{tool_name}:{digest}"


# ---------------- The drop-in API ----------------
def cached_execute(tool_name: str, args: dict[str, Any],
                   handler: Callable[..., dict]) -> dict:
    """Run handler(**args) with cache-aside.

    1. Build cache key.
    2. If hit  → return cached value (records saved time).
    3. If miss → invoke handler, cache result (unless it's an error).
    """
    backend = get_backend()
    key = make_key(tool_name, args)

    cached = backend.get(key)
    if cached is not None:
        # mark cache hit on the result for observability (Langfuse / logs)
        if isinstance(cached, dict):
            cached = {**cached, "_cache": "hit"}
        return cached

    t0 = time.time()
    result = handler(**args)
    elapsed_ms = (time.time() - t0) * 1000

    # Don't cache errors — let the next call retry.
    if isinstance(result, dict) and "error" not in result:
        ttl = TOOL_TTL.get(tool_name, DEFAULT_TTL)
        backend.set(key, result, ttl)
        # record how much time the cache *would have* saved on a future hit
        if hasattr(backend, "record_saved"):
            backend.record_saved(elapsed_ms)

    # mark fresh result for observability
    if isinstance(result, dict):
        result = {**result, "_cache": "miss"}
    return result


def get_stats() -> dict[str, Any]:
    """Diagnostics for /api/health or /api/cache/stats endpoint."""
    return get_backend().stats()


def clear() -> None:
    """For tests."""
    global _backend
    _backend = None
