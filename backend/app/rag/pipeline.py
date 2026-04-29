"""End-to-end retrieval: query → dense vector search → rerank → top-k chunks.

Optional metadata filter for precision (e.g. only currency=JPY).
"""
from __future__ import annotations

from typing import Iterable

from . import store
from .config import RETRIEVE_K, RERANK_K, MIN_RERANK_SCORE
from .embedder import embed_one
from .reranker import rerank


def retrieve(query: str,
             k: int = RERANK_K,
             pool: int = RETRIEVE_K,
             where: dict | None = None,
             min_score: float = MIN_RERANK_SCORE) -> list[dict]:
    """Return list of {text, source_file, title, category, currency, score}."""
    # 1. dense recall
    qvec = embed_one(query)
    hits = store.query(qvec, k=pool, where=where)
    if not hits["ids"][0]:
        return []

    docs = hits["documents"][0]
    metas = hits["metadatas"][0]
    distances = hits["distances"][0]

    # 2. rerank
    scores = rerank(query, docs)
    candidates = [
        {**m, "text": d, "dense_distance": dist, "rerank_score": s}
        for d, m, dist, s in zip(docs, metas, distances, scores)
    ]
    candidates.sort(key=lambda x: x["rerank_score"], reverse=True)

    # 3. cut by min_score and top-k
    out = [c for c in candidates if c["rerank_score"] >= min_score][:k]
    return out


def format_citations(chunks: list[dict]) -> str:
    """Render chunks as a context block for prompt injection."""
    if not chunks:
        return ""
    lines = ["以下是从知识库检索到的相关内容（按相关度排序）：\n"]
    for i, c in enumerate(chunks, 1):
        lines.append(f"[来源 {i}] {c.get('title', c.get('source_file'))}"
                     f" (rerank={c.get('rerank_score', 0):.2f})\n")
        lines.append(c["text"])
        lines.append("")
    return "\n".join(lines)
