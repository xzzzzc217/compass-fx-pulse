"""Phase 4.2 — runs the Agent against a single golden-set question.

Two execution modes:
- DIRECT: import stream_agent and consume the generator (fast, in-process)
- HTTP:   GET /api/agent?query=... (matches production, slower)

Default is DIRECT for speed. Use --http to test against a running server.
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Any

# Allow `python eval/runner.py` from backend/
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def parse_sse_line(line: str) -> dict | None:
    """Parse one SSE-format line: 'data: {...}'."""
    if not line.startswith("data: "):
        return None
    body = line[6:].strip()
    if not body:
        return None
    try:
        return json.loads(body)
    except json.JSONDecodeError:
        return None


def collect_run(events) -> dict:
    """Consume an iterable of SSE strings, collect into structured run record."""
    text_parts: list[str] = []
    tools_called: list[dict] = []
    plans: list[dict] = []
    errors: list[str] = []

    for raw in events:
        # raw can be either an already-parsed dict (direct mode) or
        # a raw SSE-format string (HTTP mode).
        if isinstance(raw, dict):
            obj = raw
        elif isinstance(raw, str):
            # raw could contain multiple "data: ..." lines
            for line in raw.splitlines():
                obj = parse_sse_line(line)
                if obj is None:
                    continue
                _route_event(obj, text_parts, tools_called, plans, errors)
            continue
        else:
            continue
        _route_event(obj, text_parts, tools_called, plans, errors)

    return {
        "text": "".join(text_parts),
        "tools_called": tools_called,
        "plans": plans,
        "errors": errors,
    }


def _route_event(obj: dict, text_parts, tools_called, plans, errors):
    if "trace" in obj:
        tr = obj["trace"]
        kind = tr.get("kind", "")
        if kind == "plan":
            plans.append(tr)
        elif kind == "tool_result":
            tools_called.append({
                "name": tr["name"],
                "args": tr.get("args", {}),
                "result": tr.get("result", {}),
                "exec_ms": tr.get("tool_exec_ms", 0),
            })
        elif kind == "reflect":
            tr.setdefault("kind", "reflect")
            plans.append(tr)
        elif kind == "error":
            errors.append(tr.get("message", "unknown error"))
    elif "text" in obj:
        t = obj["text"]
        if t == "[DONE]":
            return
        if t.startswith("[ERROR]"):
            errors.append(t)
            return
        text_parts.append(t)


def run_direct(query: str, *, disable_reflector: bool = False,
               disable_rag: bool = False) -> dict:
    """Execute the agent in-process and return a structured run record.

    Setting disable_reflector / disable_rag does ablation by env override.
    """
    if disable_reflector:
        os.environ["REFLECTOR_DISABLED"] = "1"
    if disable_rag:
        os.environ["RAG_DISABLED"] = "1"

    from app.agent.core import stream_agent

    t0 = time.time()
    sse_strings = list(stream_agent(query, emit_trace=True))
    elapsed_ms = (time.time() - t0) * 1000

    run = collect_run(sse_strings)
    run["latency_ms"] = round(elapsed_ms, 1)
    run["query"] = query
    run["mode"] = "direct"
    run["ablation"] = {
        "no_reflector": disable_reflector,
        "no_rag": disable_rag,
    }
    return run


def run_http(query: str, base_url: str = "http://127.0.0.1:8080") -> dict:
    """Execute via HTTP (matches production traffic shape)."""
    import requests
    from urllib.parse import quote

    url = f"{base_url}/api/agent?query={quote(query)}&trace=1"
    t0 = time.time()
    with requests.get(url, stream=True, timeout=180) as resp:
        if resp.status_code != 200:
            return {"error": f"HTTP {resp.status_code}: {resp.text[:200]}",
                    "query": query, "mode": "http"}
        events = []
        for raw in resp.iter_lines():
            if raw:
                events.append(raw.decode("utf-8"))

    elapsed_ms = (time.time() - t0) * 1000
    run = collect_run(events)
    run["latency_ms"] = round(elapsed_ms, 1)
    run["query"] = query
    run["mode"] = "http"
    return run


if __name__ == "__main__":
    # Smoke test
    q = sys.argv[1] if len(sys.argv) > 1 else "什么是 carry trade?"
    print(json.dumps(run_direct(q), ensure_ascii=False, indent=2))
