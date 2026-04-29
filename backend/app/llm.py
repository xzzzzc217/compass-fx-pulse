"""LLM clients — heterogeneous routing per endpoint.

Two roles, configured independently in .env:
  - CHAT  (/api/messages, "慧聚答疑")           — single-turn LLM chat
  - AGENT (/api/agent, "智能助手")              — Function Calling, needs tools-capable model

Both are OpenAI-compatible so we can mix-and-match: e.g.
  CHAT  → local LoRA serve on :8001 (showcase fine-tuned Qwen3-1.7B)
  AGENT → DeepSeek cloud (needs tools API)
"""
import json
from typing import Iterable

import httpx
from openai import OpenAI

from .config import settings

_chat_client: OpenAI | None = None
_agent_client: OpenAI | None = None


def _is_localhost(url: str) -> bool:
    return any(host in url for host in ("127.0.0.1", "localhost", "::1"))


def _build_client(api_key: str, base_url: str, role: str) -> OpenAI:
    """OpenAI client that bypasses HTTP_PROXY env vars when base_url is local.

    Without this, users running Clash/V2Ray/etc. on Windows hit 403 because
    OpenAI SDK's httpx.Client picks up HTTP_PROXY but doesn't respect NO_PROXY,
    routing localhost calls through their VPN proxy which then rejects them.
    """
    if not api_key:
        raise RuntimeError(
            f"LLM_{role.upper()}_API_KEY (or LLM_API_KEY) is empty. Set in backend/.env."
        )
    if _is_localhost(base_url):
        # trust_env=False ignores HTTP_PROXY / HTTPS_PROXY / NO_PROXY entirely
        http_client = httpx.Client(trust_env=False, timeout=120.0)
        return OpenAI(api_key=api_key, base_url=base_url, http_client=http_client)
    return OpenAI(api_key=api_key, base_url=base_url)


def get_chat_client() -> OpenAI:
    global _chat_client
    if _chat_client is None:
        _chat_client = _build_client(
            settings.LLM_CHAT_API_KEY, settings.LLM_CHAT_BASE_URL, "chat"
        )
    return _chat_client


def get_agent_client() -> OpenAI:
    global _agent_client
    if _agent_client is None:
        _agent_client = _build_client(
            settings.LLM_AGENT_API_KEY, settings.LLM_AGENT_BASE_URL, "agent"
        )
    return _agent_client


def stream_chat(user_text: str) -> Iterable[str]:
    """Yield SSE-encoded text chunks. Used by /api/messages (慧聚答疑).

    Wire format:
        data: {"text": "..."}\n\n
        ...
        data: {"text": "[DONE]"}\n\n
    """
    # Local LoRA on a laptop GPU is much slower than DeepSeek cloud;
    # cap max_tokens for /ai so users don't wait minutes for a 2000-token answer.
    is_local = _is_localhost(settings.LLM_CHAT_BASE_URL)
    cap = 600 if is_local else settings.LLM_MAX_TOKENS

    try:
        completion = get_chat_client().chat.completions.create(
            model=settings.LLM_CHAT_MODEL,
            messages=[
                {"role": "system", "content": settings.SYSTEM_PROMPT},
                {"role": "user", "content": user_text},
            ],
            temperature=settings.LLM_TEMPERATURE,
            max_tokens=cap,
            stream=True,
        )
        for chunk in completion:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta
            piece = (delta.content or "") if delta else ""
            if piece:
                yield f"data: {json.dumps({'text': piece}, ensure_ascii=False)}\n\n"
        yield f"data: {json.dumps({'text': '[DONE]'}, ensure_ascii=False)}\n\n"
    except Exception as exc:
        err = json.dumps({"text": f"[ERROR] {exc}"}, ensure_ascii=False)
        yield f"data: {err}\n\n"
        yield f"data: {json.dumps({'text': '[DONE]'}, ensure_ascii=False)}\n\n"
