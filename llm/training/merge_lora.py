"""Merge the trained LoRA adapter back into the base model.

Output is a full-weight model that vLLM / transformers can load without peft.
"""
from __future__ import annotations

import shutil
from pathlib import Path

import torch
from peft import PeftModel
from transformers import AutoModelForCausalLM, AutoTokenizer

ROOT = Path(__file__).resolve().parent.parent  # llm/
BASE = ROOT / "models" / "Qwen3-1.7B"
ADAPTER = ROOT / "output" / "lora-qwen3-1.7b" / "final"
MERGED = ROOT / "output" / "qwen3-1.7b-finance-merged"


def main() -> None:
    if not ADAPTER.exists():
        raise SystemExit(f"Adapter not found: {ADAPTER}\nRun train_lora.py first.")

    print(f"Base:    {BASE}")
    print(f"Adapter: {ADAPTER}")
    print(f"Merged:  {MERGED}")
    print()

    # IMPORTANT: load base in fp16/bf16 (NOT 4-bit) for merging,
    # otherwise the dequantization → merge step is lossy.
    print("[1/3] Loading base in BF16 ...")
    base = AutoModelForCausalLM.from_pretrained(
        str(BASE),
        torch_dtype=torch.bfloat16,
        device_map="auto",
        trust_remote_code=True,
    )

    print("[2/3] Attaching adapter and merging ...")
    model = PeftModel.from_pretrained(base, str(ADAPTER))
    merged = model.merge_and_unload()

    print(f"[3/3] Saving to {MERGED} ...")
    MERGED.mkdir(parents=True, exist_ok=True)
    merged.save_pretrained(str(MERGED), safe_serialization=True, max_shard_size="2GB")
    tok = AutoTokenizer.from_pretrained(str(BASE), trust_remote_code=True)
    tok.save_pretrained(str(MERGED))

    # copy any tokenizer/template files the base ships
    for name in ("chat_template.jinja", "generation_config.json"):
        src = BASE / name
        if src.exists():
            shutil.copy2(src, MERGED / name)

    print(f"\nDone. Merged model ready at {MERGED}")
    print("Next: vllm serve <merged_path> --port 8000")


if __name__ == "__main__":
    main()
