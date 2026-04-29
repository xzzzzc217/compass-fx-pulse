from flask import Blueprint, jsonify

from .config import settings
from .db import get_cursor

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
    })
