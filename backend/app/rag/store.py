"""ChromaDB persistent client. Stores chunks with metadata.

Why Chroma:
  - pip install only, no Docker
  - Persistent on-disk SQLite + DuckDB
  - Native cosine similarity
  - Production swap-out to Qdrant/Milvus is trivial (same Document + filter API)
"""
from __future__ import annotations

import chromadb
from chromadb.config import Settings

from .config import CHROMA_DIR, COLLECTION

_client = None
_coll = None


def get_client():
    global _client
    if _client is None:
        CHROMA_DIR.mkdir(parents=True, exist_ok=True)
        _client = chromadb.PersistentClient(
            path=str(CHROMA_DIR),
            settings=Settings(anonymized_telemetry=False),
        )
    return _client


def get_collection():
    global _coll
    if _coll is None:
        _coll = get_client().get_or_create_collection(
            name=COLLECTION,
            metadata={"hnsw:space": "cosine"},
        )
    return _coll


def reset_collection() -> None:
    """Delete and recreate the collection (used by ingest --rebuild)."""
    global _coll
    client = get_client()
    try:
        client.delete_collection(name=COLLECTION)
    except Exception:
        pass
    _coll = client.get_or_create_collection(
        name=COLLECTION,
        metadata={"hnsw:space": "cosine"},
    )


def upsert(ids: list[str], embeddings: list[list[float]],
           documents: list[str], metadatas: list[dict]) -> None:
    coll = get_collection()
    coll.upsert(
        ids=ids,
        embeddings=embeddings,
        documents=documents,
        metadatas=metadatas,
    )


def query(embedding: list[float], k: int,
          where: dict | None = None) -> dict:
    """Returns {ids, documents, metadatas, distances}. Lower distance = closer."""
    coll = get_collection()
    return coll.query(
        query_embeddings=[embedding],
        n_results=k,
        where=where,
    )


def count() -> int:
    return get_collection().count()
