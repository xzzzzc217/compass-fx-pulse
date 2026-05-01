"""Phase 4.4 — FastAPI ASGI entry point.

Run:
    cd backend
    uvicorn main_fastapi:app --host 0.0.0.0 --port 8082 --workers 1

For real concurrency benchmark, use multiple workers:
    uvicorn main_fastapi:app --host 0.0.0.0 --port 8082 --workers 4

vs Flask (Phase 3 / 4.1):
    python main.py   # Flask, port 8080, threaded=False
"""
import os

# Same Windows + PyTorch hardening as main.py (must be first!)
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")

from app.routes_async import create_fastapi_app

app = create_fastapi_app()


if __name__ == "__main__":
    import uvicorn

    # Pre-warm RAG models so the first /api/agent call isn't 60s cold start
    try:
        import torch
        torch.set_num_threads(1)
        torch.set_num_interop_threads(1)
    except Exception:
        pass

    print("[warmup] loading bge-m3 + reranker (this is the slow part)...", flush=True)
    try:
        from app.rag.embedder import embed_one
        from app.rag.reranker import rerank
        embed_one("warmup")
        rerank("warmup", ["a", "b"])
        print("[warmup] RAG ready", flush=True)
    except Exception as e:
        print(f"[warmup] skipped: {e}", flush=True)

    uvicorn.run(
        "main_fastapi:app",
        host="0.0.0.0",
        port=int(os.environ.get("FASTAPI_PORT", "8082")),
        # workers=1 is intentional for the demo; we want to show ONE process
        # serving N concurrent users via asyncio, not N processes each
        # serving 1.  Multi-worker is for production gunicorn-style scaling.
        workers=1,
        log_level="info",
        access_log=False,  # silence per-request logs during bench
    )
