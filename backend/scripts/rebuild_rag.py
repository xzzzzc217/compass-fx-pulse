"""CLI to (re)build the RAG index. Convenience wrapper around app.rag.ingest."""
from __future__ import annotations

import os
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
os.environ.setdefault("OMP_NUM_THREADS", "1")

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.rag.ingest import ingest_corpus  # noqa: E402
from app.rag import store, pipeline  # noqa: E402


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--rebuild", action="store_true",
                   help="drop collection and rebuild from scratch")
    p.add_argument("--query", type=str, default=None,
                   help="after ingest, run a smoke query and print top-5 hits")
    args = p.parse_args()

    ingest_corpus(rebuild=args.rebuild)
    print(f"\nCollection size: {store.count()} chunks")

    if args.query:
        print(f"\n=== Smoke query: {args.query!r} ===")
        hits = pipeline.retrieve(args.query, k=5)
        for i, h in enumerate(hits, 1):
            print(f"\n[{i}] score={h['rerank_score']:.3f}  {h['title']}  ({h['source_file']})")
            print(f"    {h['text'][:200]}...")


if __name__ == "__main__":
    main()
