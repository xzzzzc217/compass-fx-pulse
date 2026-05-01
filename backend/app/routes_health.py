from flask import Blueprint, jsonify

from .cache import get_stats as cache_stats
from .config import settings
from .db import get_cursor
from .rate_limit import get_default as get_rate_limiter

bp = Blueprint("health", __name__)


@bp.get("/api/health")
def health():
    db_ok = False
    db_err = None
    try:
        with get_cursor() as cur:
            cur.execute("SELECT 1")
            cur.fetchone()
            db_ok = True
    except Exception as exc:
        db_err = str(exc)

    return jsonify({
        "status": "ok" if db_ok else "degraded",
        "db": {"ok": db_ok, "error": db_err},
        "llm_chat": {
            "base_url": settings.LLM_CHAT_BASE_URL,
            "model": settings.LLM_CHAT_MODEL,
            "key_loaded": bool(settings.LLM_CHAT_API_KEY),
        },
        "llm_agent": {
            "base_url": settings.LLM_AGENT_BASE_URL,
            "model": settings.LLM_AGENT_MODEL,
            "key_loaded": bool(settings.LLM_AGENT_API_KEY),
        },
        # Phase 4.1 — caching + rate-limiting visibility
        "cache": cache_stats(),
        "rate_limit": get_rate_limiter().stats(),
    })


@bp.get("/api/cache/stats")
def cache_stats_endpoint():
    """Lightweight endpoint just for cache observability."""
    return jsonify(cache_stats())
