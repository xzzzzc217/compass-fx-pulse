"""bge-m3 dense embedding using raw transformers (most stable on Windows).

Why not sentence_transformers / FlagEmbedding:
  - sentence_transformers + bge-m3 segfaults silently on some Windows + transformers 5.x setups
  - FlagEmbedding 1.4 calls APIs removed in transformers 5.x

Strategy: load bge-m3 as a plain XLMRobertaModel, do CLS pooling + L2 normalize.
This matches bge-m3's official dense embedding output.
"""
from __future__ import annotations

import os

from .config import EMBEDDER_PATH

_tokenizer = None
_model = None
_device = None
_torch = None  # cached torch module


def _ensure_loaded():
    global _tokenizer, _model, _device, _torch
    if _model is not None:
        return
    import sys
    print(f"[embedder] loading {EMBEDDER_PATH}", file=sys.stderr, flush=True)

    import torch
    from transformers import AutoModel, AutoTokenizer
    _torch = torch

    _tokenizer = AutoTokenizer.from_pretrained(EMBEDDER_PATH, use_fast=True)
    _device = os.getenv("RAG_EMBEDDER_DEVICE", "cpu").lower()
    if _device == "cuda" and not torch.cuda.is_available():
        _device = "cpu"
    dtype = torch.float16 if _device == "cuda" else torch.float32
    _model = AutoModel.from_pretrained(EMBEDDER_PATH, torch_dtype=dtype)
    _model = _model.to(_device).eval()
    print(f"[embedder] ready on {_device}", file=sys.stderr, flush=True)


def embed(texts: list[str], batch_size: int = 8,
          show_progress: bool | None = None) -> list[list[float]]:
    """Encode texts to L2-normalized 1024-dim CLS-pooled vectors.

    show_progress: None → auto (on if len > 16), True/False to force.
    """
    _ensure_loaded()
    torch = _torch

    if show_progress is None:
        show_progress = len(texts) > 16

    iterator = range(0, len(texts), batch_size)
    if show_progress:
        try:
            from tqdm import tqdm
            iterator = tqdm(list(iterator), desc="embedding", unit="batch")
        except ImportError:
            pass

    out: list[list[float]] = []
    with torch.no_grad():
        for i in iterator:
            batch = texts[i: i + batch_size]
            inputs = _tokenizer(
                batch,
                padding=True, truncation=True, max_length=512,
                return_tensors="pt",
            ).to(_device)
            hidden = _model(**inputs, return_dict=True).last_hidden_state
            cls = hidden[:, 0, :]
            cls = torch.nn.functional.normalize(cls, p=2, dim=1)
            out.extend(cls.float().cpu().tolist())
    return out


def embed_one(text: str) -> list[float]:
    return embed([text])[0]
