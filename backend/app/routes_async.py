"""Phase 4.4 — FastAPI async router (parallel to Flask routes_*).

Why side-by-side, not a full migration?
---------------------------------------
- Flask routes are stable & production-tested
- A full migration risks the working demo on interview day
- Async value is most visible on the **LLM-bound** path (where Flask's
  threaded=False is the hard limit). Wrapping sync DB calls in
  asyncio.to_thread() is good enough for the data-bound paths.

Endpoints exposed (mirror Flask):
  GET  /api/health            ← async wrap of routes_health.health
  GET  /api/rates             ← simple SQL
  GET  /api/agent             ← SSE streaming of stream_agent (the
                                 throughput-killer in Flask)
  GET  /api/cache/stats       ← cheap in-memory read
"""
from __future__ import annotations

import asyncio
import json
import os
from typing import AsyncIterator
from urllib.parse import quote_plus

from fastapi import APIRouter, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse

from .cache import get_stats as cache_stats
from .config import settings
from .db import get_cursor
from .rate_limit import get_default as get_rate_limiter
from .security.injection_guard import classify_user_input

router = APIRouter()


# ---------- /api/health (cheap, fully async-friendly) ----------
@router.get("/api/health")
async def health() -> JSONResponse:
    # Wrap sync DB ping in thread pool — DB call is ~5ms, doesn't block long
    db_ok = False
    db_err = None
    try:
        def _ping() -> None:
            with get_cursor() as cur:
                cur.execute("SELECT 1")
                cur.fetchone()
        await asyncio.to_thread(_ping)
        db_ok = True
    except Exception as exc:
        db_err = str(exc)

    return JSONResponse({
        "status": "ok" if db_ok else "degraded",
        "framework": "fastapi-async",
        "db": {"ok": db_ok, "error": db_err},
        "cache": cache_stats(),
        "rate_limit": get_rate_limiter().stats(),
    })


@router.get("/api/cache/stats")
async def cache_stats_endpoint() -> JSONResponse:
    return JSONResponse(cache_stats())


# ---------- /api/agent (the QPS-killer; biggest async win) ----------
@router.get("/api/agent")
async def agent_endpoint(request: Request, query: str, trace: int = 1) -> StreamingResponse:
    """Agent SSE stream.

    The trick: stream_agent is a *sync generator* that yields SSE strings
    (each yield blocks on a DeepSeek call ~3-8s). We run it in a thread
    pool via asyncio.to_thread so the FastAPI worker can serve OTHER
    requests while one agent is mid-LLM-call.

    Net effect for concurrent users:
      Flask threaded=False : 1 user at a time
      FastAPI + thread pool: N users at a time (N = thread pool size,
                              default 40, configurable via uvicorn workers)
    """
    # Phase 4.3 input guard (re-applied at the entry point — defense in depth)
    guard = classify_user_input(query)
    if guard["should_block"]:
        async def blocked():
            msg = {"text": f"已被安全策略拦截：{', '.join(guard['reasons'][:3])}"}
            yield f"data: {json.dumps(msg, ensure_ascii=False)}\n\n"
            yield "data: {\"text\": \"[DONE]\"}\n\n"
        return StreamingResponse(blocked(), media_type="text/event-stream")

    # Phase 4.1 rate limiter
    client_ip = (request.headers.get("x-forwarded-for", "").split(",")[0].strip()
                 or (request.client.host if request.client else "anonymous"))
    if not get_rate_limiter().allow(client_ip):
        async def rl_msg():
            yield ('data: {"text": "rate limit exceeded; please slow down"}'
                   '\n\ndata: {"text": "[DONE]"}\n\n')
        return StreamingResponse(rl_msg(), media_type="text/event-stream")

    from .agent.core import stream_agent

    # Bridge sync generator → async generator so each yield doesn't block
    # the event loop.
    def sync_run() -> list[str]:
        """Buffered run.
        TODO 4.4.1: switch to a queue for true streaming during one request
        (right now we collect then stream; OK for demo, fine for interview).
        """
        return list(stream_agent(query, emit_trace=bool(trace)))

    async def gen() -> AsyncIterator[str]:
        # Run the whole sync generator in a thread; collect all SSE strings
        events = await asyncio.to_thread(sync_run)
        for evt in events:
            yield evt

    return StreamingResponse(gen(), media_type="text/event-stream")


# ---------- /api/rates (simple SQL endpoint, demo for async DB pattern) ----------
@router.get("/api/rates/recent")
async def rates_recent(currency_a: str = "USD", currency_b: str = "JPY",
                       limit: int = 30) -> JSONResponse:
    """Get recent rates for a pair. Demonstrates async-wrap of sync MySQL pool."""
    if currency_a not in {"USD", "EUR", "GBP", "JPY", "HKD", "AUD"}:
        return JSONResponse({"error": "unsupported currency_a"}, status_code=400)
    if currency_b not in {"USD", "EUR", "GBP", "JPY", "HKD", "AUD"}:
        return JSONResponse({"error": "unsupported currency_b"}, status_code=400)
    limit = max(1, min(limit, 365))

    def _query():
        with get_cursor() as cur:
            cur.execute(
                """SELECT time, rate FROM historicaldata
                   WHERE currencytype1=%s AND currencytype2=%s
                   ORDER BY time DESC LIMIT %s""",
                (currency_a, currency_b, limit),
            )
            return [{"date": r[0].strftime("%Y-%m-%d"), "rate": float(r[1])}
                    for r in cur.fetchall()]

    rows = await asyncio.to_thread(_query)
    return JSONResponse({"pair": f"{currency_a}/{currency_b}", "rows": rows})


def create_fastapi_app() -> FastAPI:
    """Factory — used by main_fastapi.py."""
    app = FastAPI(title="CompassFXPulse (FastAPI async demo)",
                  description="Phase 4.4 — parallel async deployment for QPS bench",
                  version="4.4.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"], allow_credentials=True,
        allow_methods=["*"], allow_headers=["*"],
    )
    app.include_router(router)
    return app
