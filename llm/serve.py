"""OpenAI-compatible inference server for the fine-tuned Qwen3-1.7B-Finance.

Why FastAPI + transformers (vs vLLM):
    vLLM is Linux-only as of 2026; we serve from Windows directly so the demo
    works on the laptop without WSL. The wire format is OpenAI-compatible, so
    swapping to `vllm serve` later is a one-line change in backend/.env
    (LLM_BASE_URL → http://wsl-ip:8000/v1).

Endpoints:
    POST /v1/chat/completions         (streaming + non-streaming)
    GET  /v1/models                   (lists "qwen3-1.7b-finance")
    GET  /healthz

Usage:
    python serve.py                                  # serves merged model on :8001
    python serve.py --model models/Qwen3-1.7B        # serve base instead
    python serve.py --port 9000

Then in backend/.env:
    LLM_PROVIDER=local-lora
    LLM_BASE_URL=http://127.0.0.1:8001/v1
    LLM_MODEL=qwen3-1.7b-finance
    LLM_API_KEY=local-no-auth-needed
"""
from __future__ import annotations

import argparse
import asyncio
import json
import time
import uuid
from pathlib import Path
from threading import Thread
from typing import AsyncIterator

import torch
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from transformers import AutoModelForCausalLM, AutoTokenizer, TextIteratorStreamer

ROOT = Path(__file__).resolve().parent
MERGED = ROOT / "output" / "qwen3-1.7b-finance-merged"
BASE = ROOT / "models" / "Qwen3-1.7B"
SERVED_NAME = "qwen3-1.7b-finance"


# ---------- OpenAI request schema (subset we actually use) ----------
class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    model: str = SERVED_NAME
    messages: list[ChatMessage]
    temperature: float = 0.7
    top_p: float = 0.9
    max_tokens: int = Field(default=1024, alias="max_tokens")
    stream: bool = False
    # Qwen3-specific: opt out of thinking mode for low-latency chat
    enable_thinking: bool = False

    class Config:
        populate_by_name = True


# ---------- App + globals ----------
app = FastAPI(title="CompassFX Local LLM")
_tokenizer = None
_model = None
_device = None
_model_path = None


def _load(path: Path, quant: str = "bf16") -> None:
    """quant: 'bf16' (full precision, ~3.4GB) or '4bit' (NF4, ~1.2GB, ~2x faster on 4060)."""
    global _tokenizer, _model, _device, _model_path
    print(f"Loading {path} (quant={quant}) ...")
    _tokenizer = AutoTokenizer.from_pretrained(str(path), trust_remote_code=True)

    kwargs = dict(device_map="auto", trust_remote_code=True)
    if quant == "4bit":
        from transformers import BitsAndBytesConfig
        kwargs["quantization_config"] = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_use_double_quant=True,
            bnb_4bit_compute_dtype=torch.bfloat16,
        )
    else:
        kwargs["torch_dtype"] = torch.bfloat16

    _model = AutoModelForCausalLM.from_pretrained(str(path), **kwargs)
    _model.eval()
    _device = next(_model.parameters()).device
    _model_path = path
    print(f"Ready on {_device}.")


def _prep_inputs(messages: list[dict], enable_thinking: bool):
    text = _tokenizer.apply_chat_template(
        messages,
        add_generation_prompt=True,
        tokenize=False,
        enable_thinking=enable_thinking,
    )
    inputs = _tokenizer([text], return_tensors="pt").to(_device)
    return inputs


def _gen_kwargs(req: ChatRequest, streamer=None) -> dict:
    # Hot-path: keep this lean. repetition_penalty on a 152k-vocab model
    # adds ~30-50% per-token overhead and rarely improves quality; skip it.
    sampling = req.temperature > 0.05  # essentially zero → greedy
    kw = dict(
        max_new_tokens=req.max_tokens,
        do_sample=sampling,
        pad_token_id=_tokenizer.pad_token_id or _tokenizer.eos_token_id,
        use_cache=True,
    )
    if sampling:
        kw["temperature"] = req.temperature
        kw["top_p"] = req.top_p
    if streamer is not None:
        kw["streamer"] = streamer
    return kw


# ---------- Endpoints ----------
@app.get("/healthz")
def healthz():
    return {"status": "ok", "model": str(_model_path), "device": str(_device)}


@app.get("/v1/models")
def list_models():
    return {
        "object": "list",
        "data": [{"id": SERVED_NAME, "object": "model",
                  "created": int(time.time()), "owned_by": "compass-fx"}],
    }


def _completion_id() -> str:
    return f"chatcmpl-{uuid.uuid4().hex[:24]}"


@app.post("/v1/chat/completions")
async def chat_completions(req: ChatRequest):
    if _model is None:
        raise HTTPException(503, "model not loaded yet")
    msgs = [m.model_dump() for m in req.messages]
    inputs = _prep_inputs(msgs, req.enable_thinking)
    cmpl_id = _completion_id()
    created = int(time.time())

    if not req.stream:
        with torch.no_grad():
            out = _model.generate(**inputs, **_gen_kwargs(req))
        ans = _tokenizer.decode(out[0][inputs.input_ids.shape[-1]:],
                                skip_special_tokens=True)
        return {
            "id": cmpl_id,
            "object": "chat.completion",
            "created": created,
            "model": SERVED_NAME,
            "choices": [{
                "index": 0,
                "message": {"role": "assistant", "content": ans},
                "finish_reason": "stop",
            }],
            "usage": {
                "prompt_tokens": inputs.input_ids.shape[-1],
                "completion_tokens": out.shape[-1] - inputs.input_ids.shape[-1],
                "total_tokens": out.shape[-1],
            },
        }

    streamer = TextIteratorStreamer(
        _tokenizer, skip_prompt=True, skip_special_tokens=True
    )
    gen_thread = Thread(
        target=_model.generate,
        kwargs={**inputs, **_gen_kwargs(req, streamer)},
    )
    gen_thread.start()

    async def event_stream() -> AsyncIterator[str]:
        # First chunk announces role
        first = {
            "id": cmpl_id, "object": "chat.completion.chunk",
            "created": created, "model": SERVED_NAME,
            "choices": [{"index": 0, "delta": {"role": "assistant"},
                         "finish_reason": None}],
        }
        yield f"data: {json.dumps(first, ensure_ascii=False)}\n\n"

        for piece in streamer:
            if not piece:
                continue
            chunk = {
                "id": cmpl_id, "object": "chat.completion.chunk",
                "created": created, "model": SERVED_NAME,
                "choices": [{"index": 0, "delta": {"content": piece},
                             "finish_reason": None}],
            }
            yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"
            await asyncio.sleep(0)

        finish = {
            "id": cmpl_id, "object": "chat.completion.chunk",
            "created": created, "model": SERVED_NAME,
            "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
        }
        yield f"data: {json.dumps(finish, ensure_ascii=False)}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


# ---------- Boot ----------
def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    default = MERGED if MERGED.exists() else BASE
    p.add_argument("--model", default=str(default),
                   help="Path to model dir (default: merged if exists else base)")
    p.add_argument("--port", type=int, default=8001)
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--quant", choices=["bf16", "4bit"], default="bf16",
                   help="4bit (NF4) ~halves VRAM and ~2x throughput on 4060; "
                        "slight quality drop. bf16 = full precision.")
    return p.parse_args()


if __name__ == "__main__":
    args = parse_args()
    _load(Path(args.model), quant=args.quant)
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")
