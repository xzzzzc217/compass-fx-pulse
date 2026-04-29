"""Download bge-m3 + bge-reranker-v2-m3 from hf-mirror.com."""
from __future__ import annotations

import os
from pathlib import Path

os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"
os.environ["HF_HUB_ENABLE_HF_TRANSFER"] = "0"

from huggingface_hub import snapshot_download

ROOT = Path(__file__).resolve().parent.parent
MODELS = ROOT / "models"

REPOS = [
    "BAAI/bge-m3",                  # ~2.27 GB embedding (CN+EN)
    "BAAI/bge-reranker-v2-m3",      # ~568 MB reranker (CN+EN)
]


def main() -> None:
    for repo in REPOS:
        local = MODELS / repo.split("/")[-1]
        local.mkdir(parents=True, exist_ok=True)
        print(f"\n=== Downloading {repo} → {local} ===")
        snapshot_download(
            repo_id=repo,
            local_dir=str(local),
            local_dir_use_symlinks=False,
            max_workers=4,
            resume_download=True,
            ignore_patterns=[
                ".DS_Store", "**/.DS_Store",   # macOS junk causes 403 on hf-mirror
                "imgs/*", "**/imgs/*",         # marketing images
                "onnx/*", "**/onnx/*",         # ONNX exports we don't use
                "*.png", "*.jpg", "*.jpeg",
            ],
        )
        print(f"Done: {repo}")


if __name__ == "__main__":
    main()
