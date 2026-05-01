import os
# ===== Windows + PyTorch + Flask hardening =====
# These env vars MUST be set BEFORE any torch / transformers / numpy import.
# Without them, the reranker forward pass segfaults silently on Windows.
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")

from flask import Flask, jsonify, request
from flask_cors import CORS

from app.config import settings
from app.rate_limit import get_default as get_rate_limiter
from app.routes_agent import bp as agent_bp
from app.routes_chat import bp as chat_bp
from app.routes_health import bp as health_bp
from app.routes_rates import bp as rates_bp


def create_app() -> Flask:
    app = Flask(__name__)
    CORS(app)
    app.register_blueprint(health_bp)
    app.register_blueprint(rates_bp)
    app.register_blueprint(chat_bp)
    app.register_blueprint(agent_bp)

    # Phase 4.1 — per-IP rate limiting on all /api/* endpoints.
    # Configurable via env: RATE_LIMIT_RPS (default 10), RATE_LIMIT_BURST (default 20).
    # Health/cache-stats endpoints are intentionally NOT limited (used by monitoring).
    rps = float(os.environ.get("RATE_LIMIT_RPS", "10"))
    burst = int(os.environ.get("RATE_LIMIT_BURST", "20"))
    limiter = get_rate_limiter(rps=rps, burst=burst)
    EXEMPT_PREFIXES = ("/api/health", "/api/cache/stats")

    @app.before_request
    def _rate_limit_check():
        path = request.path or ""
        if not path.startswith("/api/"):
            return None
        if any(path.startswith(p) for p in EXEMPT_PREFIXES):
            return None
        client_ip = (request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
                     or request.remote_addr or "anonymous")
        if not limiter.allow(client_ip):
            return jsonify(error="rate limit exceeded",
                           hint=f"max {rps} req/sec, burst {burst}"), 429
        return None

    return app


app = create_app()


def _warmup_rag() -> None:
    """Pre-load embedder + reranker so the first /api/agent RAG call is fast.

    Without this, the first user query triggers cold loads of bge-m3 (2.27GB
    from disk → RAM) + bge-reranker (568MB → GPU), adding ~30-60s of latency.
    Pre-warming amortises that cost into Flask startup (already a known wait).
    """
    try:
        print("[warmup] loading bge-m3 ...", flush=True)
        from app.rag.embedder import embed_one
        embed_one("warmup query")
        print("[warmup] loading bge-reranker ...", flush=True)
        from app.rag.reranker import rerank
        rerank("warmup", ["a", "b"])
        print("[warmup] RAG models ready", flush=True)
    except Exception as exc:
        print(f"[warmup] skipped: {exc}", flush=True)


if __name__ == "__main__":
    # Force torch to single-thread BEFORE first request triggers torch import.
    # This + use_reloader=False are the Windows fixes for the silent segfault
    # in PyTorch forward pass when called inside a Flask request thread.
    try:
        import torch
        torch.set_num_threads(1)
        torch.set_num_interop_threads(1)
    except Exception:
        pass

    _warmup_rag()  # ~30-60s cold load done now → first user query is instant

    # use_reloader=False: Flask debug-mode reloader spawns a child process whose
    #   MKL/OpenMP thread state isn't reliably initialised on Windows, causing
    #   the reranker forward pass to segfault. Single process = stable.
    # threaded=False: same model is shared across requests; PyTorch eager mode
    #   modules aren't thread-safe.
    app.run(
        host="0.0.0.0",
        port=settings.PORT,
        debug=settings.DEBUG,
        use_reloader=False,
        threaded=False,
    )
