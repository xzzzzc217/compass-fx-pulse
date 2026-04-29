"""Smoke-test the trained model on a handful of forex prompts.

Useful for sanity-checking before bothering with vLLM. Loads the merged model
in transformers and runs greedy generation on 5 fixed prompts.
"""
from __future__ import annotations

import sys
from pathlib import Path

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

ROOT = Path(__file__).resolve().parent.parent
MERGED = ROOT / "output" / "qwen3-1.7b-finance-merged"
BASE = ROOT / "models" / "Qwen3-1.7B"

PROMPTS = [
    "什么是外汇风险？企业有哪几种应对方式？",
    "美联储加息一般会通过哪些渠道影响美元/日元汇率？",
    "请用一句话解释 carry trade。",
    "What is covered interest rate parity?",
    "VaR model — what does the 99% 1-day VaR of a USD/JPY position tell me?",
]


def main() -> None:
    target = sys.argv[1] if len(sys.argv) > 1 else None
    if target == "base":
        path = BASE
        label = "BASE Qwen3-1.7B (no fine-tune)"
    else:
        path = MERGED if MERGED.exists() else BASE
        label = "FINE-TUNED merged" if path == MERGED else "BASE (merged not yet built)"

    print(f"Loading: {path}  [{label}]")
    tok = AutoTokenizer.from_pretrained(str(path), trust_remote_code=True)
    model = AutoModelForCausalLM.from_pretrained(
        str(path),
        torch_dtype=torch.bfloat16,
        device_map="auto",
        trust_remote_code=True,
    )
    model.eval()

    for i, q in enumerate(PROMPTS, 1):
        msgs = [
            {"role": "system",
             "content": "你是 CompassFXPulse 金融助手，专注外汇行情、汇率走势与外汇风险管理。"},
            {"role": "user", "content": q},
        ]
        text = tok.apply_chat_template(
            msgs, add_generation_prompt=True, tokenize=False,
            enable_thinking=False,
        )
        inputs = tok([text], return_tensors="pt").to(model.device)
        with torch.no_grad():
            out = model.generate(
                **inputs,
                max_new_tokens=300,
                do_sample=False,
                repetition_penalty=1.05,
                pad_token_id=tok.pad_token_id or tok.eos_token_id,
            )
        ans = tok.decode(out[0][inputs.input_ids.shape[-1]:], skip_special_tokens=True)
        print(f"\n--- Q{i}: {q}\nA: {ans.strip()[:600]}")


if __name__ == "__main__":
    main()
