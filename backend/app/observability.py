"""Langfuse observability — full-link tracing for the Agent.

Designed to gracefully degrade: if LANGFUSE_PUBLIC_KEY isn't set, all calls
become no-ops. No exceptions break user requests.

Setup:
  1. Sign up at https://cloud.langfuse.com (free tier, 100k events/month)
  2. Project → Settings → API Keys → create one
  3. Add to backend/.env:
       LANGFUSE_PUBLIC_KEY=pk-lf-...
       LANGFUSE_SECRET_KEY=sk-lf-...
       LANGFUSE_HOST=https://cloud.langfuse.com   # or your self-hosted URL
  4. Restart Flask. Every /api/agent call now appears as a trace.

Usage in code:
    from .observability import obs

    with obs.trace("agent_run", input={"query": query}) as t:
        with t.span("llm_decide", model=...) as s:
            ...
            s.update(output=..., usage={...})
        with t.span("tool_exec", name="get_exchange_rate", args=...) as s:
            ...
            s.update(output=...)
        t.update(output=final_answer)
"""
from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Any, Iterator, Optional


class _NoopSpan:
    """Drop-in replacement when langfuse isn't configured."""
    def update(self, **kwargs: Any) -> None: pass
    def __enter__(self) -> "_NoopSpan": return self
    def __exit__(self, *args: Any) -> None: pass

    @contextmanager
    def span(self, name: str, **kwargs: Any) -> Iterator["_NoopSpan"]:
        yield self

    @contextmanager
    def generation(self, name: str, **kwargs: Any) -> Iterator["_NoopSpan"]:
        yield self


class _NoopObs:
    enabled: bool = False
    @contextmanager
    def trace(self, name: str, **kwargs: Any) -> Iterator[_NoopSpan]:
        yield _NoopSpan()
    def flush(self) -> None: pass


class _LangfuseObs:
    """Thin wrapper around langfuse v3 client using span context managers."""

    def __init__(self, client: Any) -> None:
        self.enabled = True
        self._client = client

    @contextmanager
    def trace(self, name: str, *, input: Any = None,
              user_id: str | None = None, **kwargs: Any) -> Iterator[Any]:
        with self._client.start_as_current_span(
            name=name,
            input=input,
            metadata={"user_id": user_id} if user_id else None,
        ) as span:
            yield _LFSpan(span, self._client)

    def flush(self) -> None:
        try:
            self._client.flush()
        except Exception:
            pass


class _LFSpan:
    def __init__(self, span: Any, client: Any) -> None:
        self._span = span
        self._client = client

    def update(self, **kwargs: Any) -> None:
        try:
            self._span.update(**kwargs)
        except Exception:
            pass

    @contextmanager
    def span(self, name: str, **kwargs: Any) -> Iterator["_LFSpan"]:
        with self._client.start_as_current_span(name=name, **kwargs) as s:
            yield _LFSpan(s, self._client)

    @contextmanager
    def generation(self, name: str, *, model: str | None = None,
                   input: Any = None, **kwargs: Any) -> Iterator["_LFSpan"]:
        with self._client.start_as_current_generation(
            name=name, model=model, input=input, **kwargs,
        ) as g:
            yield _LFSpan(g, self._client)


def _build() -> Any:
    pub = os.getenv("LANGFUSE_PUBLIC_KEY", "").strip()
    sec = os.getenv("LANGFUSE_SECRET_KEY", "").strip()
    host = os.getenv("LANGFUSE_HOST", "https://cloud.langfuse.com").strip()
    if not pub or not sec or pub == "please_fill_in":
        return _NoopObs()
    try:
        from langfuse import Langfuse
        client = Langfuse(public_key=pub, secret_key=sec, host=host)
        print(f"[obs] Langfuse enabled → {host}", flush=True)
        return _LangfuseObs(client)
    except Exception as exc:
        print(f"[obs] Langfuse init failed ({exc}); telemetry disabled.", flush=True)
        return _NoopObs()


obs = _build()
