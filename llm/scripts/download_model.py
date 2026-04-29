"""Download Qwen3-1.7B from hf-mirror.com (HuggingFace mirror for CN).

Usage:
    python scripts/download_model.py
    python scripts/download_model.py Qwen/Qwen3-4B   # alternate model

Saves to: llm/models/Qwen3-1.7B/
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# CRITICAL: must set BEFORE importing huggingface_hub
os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"
os.environ["HF_HUB_ENABLE_HF_TRANSFER"] = "0"  # avoid hf_transfer SSL issues

from huggingface_hub import snapshot_download

ROOT = Path(__file__).resolve().parent.parent
MODELS_DIR = ROOT / "models"


def main() -> None:
    repo = sys.argv[1] if len(sys.argv) > 1 else "Qwen/Qwen3-1.7B"
    local_name = repo.split("/")[-1]
    target = MODELS_DIR / local_name

    print(f"Downloading {repo}")
    print(f"  endpoint: {os.environ['HF_ENDPOINT']}")
    print(f"  target:   {target}")
    target.mkdir(parents=True, exist_ok=True)

    path = snapshot_download(
        repo_id=repo,
        local_dir=str(target),
        local_dir_use_symlinks=False,
        max_workers=4,
        # skip duplicates from past sessions
        resume_download=True,
    )
    print(f"Done: {path}")


if __name__ == "__main__":
    main()
