"""Prepare LoRA SFT dataset by mixing:
  1. gbharti/finance-alpaca (English finance Q&A, ~68K examples → sample ~3K)
  2. Self-synthesized Chinese forex SFT (built from project's news csv via DeepSeek labeling)

Output:  llm/data/train.jsonl  +  llm/data/eval.jsonl  in chat format:
    {"messages": [{"role": "system", ...}, {"role": "user", ...}, {"role": "assistant", ...}]}
"""
from __future__ import annotations

import json
import os
import random
import sys
from pathlib import Path

# Use hf-mirror for HuggingFace dataset downloads (required for CN networks)
os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
os.environ.setdefault("HF_HUB_ENABLE_HF_TRANSFER", "0")

ROOT = Path(__file__).resolve().parent.parent  # llm/
DATA_DIR = ROOT / "data"
OUT_TRAIN = DATA_DIR / "train.jsonl"
OUT_EVAL = DATA_DIR / "eval.jsonl"

SEED = 42
EVAL_RATIO = 0.05
EN_SAMPLE_SIZE = 3000  # how many finance-alpaca examples to keep

SYSTEM_PROMPT = (
    "You are CompassFXPulse Assistant, a finance expert specialized in foreign "
    "exchange markets, exchange rate analysis, and FX risk management. "
    "Be concise, professional, and clearly state when you lack real-time data."
)
SYSTEM_PROMPT_ZH = (
    "你是 CompassFXPulse 金融助手，专注外汇行情、汇率走势与外汇风险管理。"
    "回答简洁专业，遇到实时数据需求请明确说明无法获取。"
)


def _load_finance_alpaca(n: int = EN_SAMPLE_SIZE) -> list[dict]:
    """Pull finance-alpaca, convert alpaca format → chat format."""
    print(f"[1/3] Loading gbharti/finance-alpaca (sample {n}) ...")
    from datasets import load_dataset

    ds = load_dataset("gbharti/finance-alpaca", split="train")
    print(f"  total: {len(ds)} examples")

    rng = random.Random(SEED)
    indices = rng.sample(range(len(ds)), min(n, len(ds)))
    rows = []
    for i in indices:
        ex = ds[i]
        instruction = ex.get("instruction", "").strip()
        inp = ex.get("input", "").strip()
        out = ex.get("output", "").strip()
        if not instruction or not out:
            continue
        user = f"{instruction}\n\n{inp}" if inp else instruction
        rows.append({
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user},
                {"role": "assistant", "content": out},
            ]
        })
    print(f"  kept: {len(rows)}")
    return rows


def _load_zh_synth() -> list[dict]:
    """Load self-synthesized Chinese forex SFT, if it exists.

    Generated separately by scripts/synthesize_zh_sft.py — that script reads
    project crawler csvs and uses DeepSeek to produce (question, answer) pairs.
    """
    src = DATA_DIR / "zh_synth.jsonl"
    if not src.exists():
        print(f"[2/3] zh_synth.jsonl not found → skipping (run synthesize_zh_sft.py first)")
        return []
    print(f"[2/3] Loading {src} ...")
    rows = []
    with open(src, "r", encoding="utf-8") as f:
        for line in f:
            obj = json.loads(line)
            user = obj["question"]
            assistant = obj["answer"]
            rows.append({
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT_ZH},
                    {"role": "user", "content": user},
                    {"role": "assistant", "content": assistant},
                ]
            })
    print(f"  kept: {len(rows)}")
    return rows


def _split_and_save(rows: list[dict]) -> None:
    """[3/3] Shuffle, split, write to JSONL."""
    print(f"[3/3] Total examples: {len(rows)}")
    rng = random.Random(SEED)
    rng.shuffle(rows)
    n_eval = max(1, int(len(rows) * EVAL_RATIO))
    eval_rows = rows[:n_eval]
    train_rows = rows[n_eval:]

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(OUT_TRAIN, "w", encoding="utf-8") as f:
        for r in train_rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    with open(OUT_EVAL, "w", encoding="utf-8") as f:
        for r in eval_rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    print(f"  train: {len(train_rows)} → {OUT_TRAIN}")
    print(f"  eval : {len(eval_rows)} → {OUT_EVAL}")


def main() -> None:
    en = _load_finance_alpaca()
    zh = _load_zh_synth()
    rows = en + zh
    _split_and_save(rows)


if __name__ == "__main__":
    main()
