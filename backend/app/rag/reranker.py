"""bge-reranker-v2-m3 wrapper.

Native transformers implementation (not FlagEmbedding) to avoid version-skew
bugs: FlagEmbedding 1.4 calls tokenizer.prepare_for_model which transformers 5.x
removed.

Device policy: defaults to CPU to avoid competing with the embedder + Flask LLM
loads on an 8 GB laptop GPU. Override with `RAG_RERANKER_DEVICE=cuda` if you have
spare VRAM.
"""
from __future__ import annotations

import os

from .config import RERANKER_PATH, RERANK_MAX_LENGTH

_tokenizer = None
_model = None
_device = None


def _ensure_loaded():
    global _tokenizer, _model, _device
    if _model is not None:
        return
    import torch
    from transformers import AutoModelForSequenceClassification, AutoTokenizer

    _tokenizer = AutoTokenizer.from_pretrained(RERANKER_PATH, use_fast=True)
    target = os.getenv("RAG_RERANKER_DEVICE", "cpu").lower()
    if target == "cuda" and not torch.cuda.is_available():
        target = "cpu"
    dtype = torch.float16 if target == "cuda" else torch.float32
    _model = AutoModelForSequenceClassification.from_pretrained(
        RERANKER_PATH, torch_dtype=dtype,
    )
    _device = target
    _model = _model.to(_device).eval()


def rerank(query: str, passages: list[str], batch_size: int = 16) -> list[float]:
    """Score each passage against the query; returns logits as-is.
    Higher = more relevant. Roughly 0 = neutral, > 0 = relevant, < 0 = irrelevant.
    """
    if not passages:
        return []
    _ensure_loaded()

    import torch

    pairs = [[query, p] for p in passages]
    scores: list[float] = []
    with torch.no_grad():
        for i in range(0, len(pairs), batch_size):
            batch = pairs[i: i + batch_size]
            inputs = _tokenizer(
                batch,
                padding=True,
                truncation=True,
                max_length=RERANK_MAX_LENGTH,
                return_tensors="pt",
            ).to(_device)
            logits = _model(**inputs, return_dict=True).logits
            # logits shape: [batch, 1] (single-label classification head)
            scores.extend(logits.view(-1).float().cpu().tolist())
    return scores
