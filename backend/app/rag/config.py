"""RAG-specific paths + tunables."""
from pathlib import Path
import os

ROOT = Path(__file__).resolve().parent.parent.parent  # backend/
DATA_DIR = ROOT / "data" / "rag"
CORPUS_DIR = DATA_DIR / "corpus"
CHROMA_DIR = DATA_DIR / "chroma"
COLLECTION = "compass_fx_kb"

# Models — point to the local snapshots downloaded by llm/scripts/download_rag_models.py
LLM_MODELS_DIR = ROOT.parent / "llm" / "models"
EMBEDDER_PATH = os.getenv("RAG_EMBEDDER", str(LLM_MODELS_DIR / "bge-m3"))
RERANKER_PATH = os.getenv("RAG_RERANKER", str(LLM_MODELS_DIR / "bge-reranker-v2-m3"))

# Tuning — sized for CPU inference latency on a laptop
CHUNK_MAX_CHARS = 600           # ~400 zh tokens or ~150 en tokens
CHUNK_OVERLAP_CHARS = 80
RETRIEVE_K = 10                 # dense top-k before rerank (was 20, halved for CPU speed)
RERANK_K = 4                    # top-k after rerank → returned to LLM
MIN_RERANK_SCORE = 0.0          # below this, treat as no relevant doc
RERANK_MAX_LENGTH = 384         # covers our 600-char chunks; 512 was wasteful on CPU
