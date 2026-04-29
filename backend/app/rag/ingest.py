"""Ingest: corpus markdown → chunks → embed → Chroma.

Run:
    python -m app.rag.ingest                    # incremental (skip files unchanged)
    python -m app.rag.ingest --rebuild          # drop collection and rebuild
"""
from __future__ import annotations

import argparse
import hashlib
import re
from pathlib import Path
from typing import Iterable

from . import store
from .config import CHUNK_MAX_CHARS, CHUNK_OVERLAP_CHARS, CORPUS_DIR
from .embedder import embed


# ---------- Frontmatter parser ----------

_FM_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


def _parse_frontmatter(text: str) -> tuple[dict, str]:
    """Return (metadata_dict, body_text). Tolerates missing frontmatter."""
    m = _FM_RE.match(text)
    if not m:
        return {}, text
    fm_block = m.group(1)
    body = text[m.end():]
    meta: dict[str, str] = {}
    for line in fm_block.splitlines():
        line = line.strip()
        if not line or ":" not in line:
            continue
        k, v = line.split(":", 1)
        v = v.strip().strip('"').strip("'")
        meta[k.strip()] = v
    return meta, body


# ---------- Chunker ----------

_HEADER_RE = re.compile(r"^(#{1,6})\s+", re.MULTILINE)


def _split_by_headers(body: str) -> list[str]:
    """Split markdown into header-bounded sections; each starts with a header."""
    matches = list(_HEADER_RE.finditer(body))
    if not matches:
        return [body.strip()] if body.strip() else []
    sections = []
    for i, m in enumerate(matches):
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(body)
        section = body[start:end].strip()
        if section:
            sections.append(section)
    # If preface before first header, prepend
    if matches and matches[0].start() > 0:
        preface = body[: matches[0].start()].strip()
        if preface:
            sections.insert(0, preface)
    return sections


def _split_long(text: str, max_chars: int, overlap: int) -> list[str]:
    """If text is too long, slide window by paragraphs."""
    if len(text) <= max_chars:
        return [text]
    paras = [p for p in re.split(r"\n\n+", text) if p.strip()]
    out: list[str] = []
    cur = ""
    for p in paras:
        if not cur:
            cur = p
            continue
        if len(cur) + len(p) + 2 <= max_chars:
            cur = f"{cur}\n\n{p}"
        else:
            out.append(cur)
            # overlap: keep last 'overlap' chars of cur as prefix
            tail = cur[-overlap:] if overlap > 0 else ""
            cur = f"{tail}\n\n{p}" if tail else p
    if cur:
        out.append(cur)
    # Hard fallback: any remaining > max_chars chunk gets sliced
    final: list[str] = []
    for c in out:
        if len(c) <= max_chars:
            final.append(c)
        else:
            for i in range(0, len(c), max_chars - overlap):
                final.append(c[i: i + max_chars])
    return final


def chunk_document(meta: dict, body: str,
                   max_chars: int = CHUNK_MAX_CHARS,
                   overlap: int = CHUNK_OVERLAP_CHARS) -> list[dict]:
    """Yield list of {text, char_offset, sub_idx} with the parent doc's metadata
    attached at upsert time.
    """
    sections = _split_by_headers(body)
    chunks: list[dict] = []
    char_offset = 0
    for section in sections:
        for sub_idx, piece in enumerate(_split_long(section, max_chars, overlap)):
            chunks.append({"text": piece, "char_offset": char_offset, "sub_idx": sub_idx})
            char_offset += len(piece)
    return chunks


# ---------- Top-level ingest ----------

def _doc_id(source_file: str, char_offset: int) -> str:
    h = hashlib.sha1(f"{source_file}:{char_offset}".encode("utf-8")).hexdigest()[:12]
    return f"{Path(source_file).stem}-{h}"


def ingest_corpus(rebuild: bool = False) -> None:
    files = sorted(CORPUS_DIR.glob("*.md"))
    if not files:
        print(f"No corpus files in {CORPUS_DIR}")
        print("Run scripts/synthesize_corpus.py first.")
        return

    if rebuild:
        print("Resetting Chroma collection ...")
        store.reset_collection()

    print(f"Ingesting {len(files)} corpus files ...")
    all_ids, all_texts, all_metas = [], [], []
    for fp in files:
        raw = fp.read_text(encoding="utf-8")
        meta, body = _parse_frontmatter(raw)
        chunks = chunk_document(meta, body)
        for ch in chunks:
            cid = _doc_id(fp.name, ch["char_offset"])
            all_ids.append(cid)
            all_texts.append(ch["text"])
            all_metas.append({
                "source_file": fp.name,
                "title": meta.get("title", fp.stem),
                "category": meta.get("category", "unknown"),
                "currency": meta.get("currency", ""),
                "char_offset": ch["char_offset"],
            })
        print(f"  {fp.name}: {len(chunks)} chunks")

    print(f"\nTotal chunks: {len(all_ids)}")
    print("Embedding (this may take a minute, model loads on first call) ...")
    vectors = embed(all_texts)
    store.upsert(all_ids, vectors, all_texts, all_metas)
    print(f"Upserted {len(all_ids)} chunks. Collection now has {store.count()}.")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--rebuild", action="store_true",
                   help="Drop collection and rebuild from scratch")
    args = p.parse_args()
    ingest_corpus(rebuild=args.rebuild)
