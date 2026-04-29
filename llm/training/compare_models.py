"""Side-by-side comparison: DeepSeek-Chat (cloud) vs Qwen3-1.7B base vs fine-tuned.

Output a markdown table to llm/output/comparison.md you can paste into a slide
or simply open in a markdown previewer. Excellent interview-demo asset.

Usage:
    python training/compare_models.py
    python training/compare_models.py --prompts custom_prompts.txt
"""
from __future__ import annotations

import argparse
import os
import time
from pathlib import Path

import torch
from openai import OpenAI
from transformers import AutoModelForCausalLM, AutoTokenizer

ROOT = Path(__file__).resolve().parent.parent
PROJECT = ROOT.parent
ENV_FILE = PROJECT / "backend" / ".env"
BASE = ROOT / "models" / "Qwen3-1.7B"
MERGED = ROOT / "output" / "qwen3-1.7b-finance-merged"
OUT_FILE = ROOT / "output" / "comparison.md"

DEFAULT_PROMPTS = [
    "什么是外汇风险？企业有哪几种应对方式？",
    "美联储加息一般会通过哪些渠道影响美元/日元汇率？",
    "请解释一下 carry trade，并举一个 USD/JPY 的例子。",
    "我们出口企业收的是美元，想做 6 个月远期锁汇，逻辑和定价是什么？",
    "covered interest parity 在什么情况下会失效？",
    "VaR 模型在外汇风险计量中的局限性是什么？",
    "港币联系汇率制度的运作机制是什么？金管局的工具有哪些？",
    "近期日本央行 YCC 政策对日元有什么影响？",
]


def _load_env() -> dict:
    env = {}
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()
    return env


def _ask_deepseek(client: OpenAI, model: str, prompt: str) -> tuple[str, float]:
    t0 = time.time()
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system",
             "content": "你是 CompassFXPulse 金融助手，专注外汇行情、汇率走势与外汇风险管理。回答简洁专业。"},
            {"role": "user", "content": prompt},
        ],
        temperature=0.7, max_tokens=400,
    )
    return resp.choices[0].message.content.strip(), time.time() - t0


def _ask_local(model, tok, prompt: str) -> tuple[str, float]:
    msgs = [
        {"role": "system",
         "content": "你是 CompassFXPulse 金融助手，专注外汇行情、汇率走势与外汇风险管理。回答简洁专业。"},
        {"role": "user", "content": prompt},
    ]
    text = tok.apply_chat_template(
        msgs, add_generation_prompt=True, tokenize=False, enable_thinking=False
    )
    inputs = tok([text], return_tensors="pt").to(model.device)
    t0 = time.time()
    with torch.no_grad():
        out = model.generate(
            **inputs, max_new_tokens=400, do_sample=True,
            temperature=0.7, top_p=0.9, repetition_penalty=1.05,
            pad_token_id=tok.pad_token_id or tok.eos_token_id,
        )
    ans = tok.decode(out[0][inputs.input_ids.shape[-1]:], skip_special_tokens=True)
    return ans.strip(), time.time() - t0


def _free(model) -> None:
    """Release a model's GPU memory before loading the next one."""
    del model
    import gc
    gc.collect()
    torch.cuda.empty_cache()


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--prompts", type=str, default=None,
                   help="path to a txt file, one prompt per line")
    p.add_argument("--max", type=int, default=8)
    return p.parse_args()


def main() -> None:
    args = parse_args()
    if args.prompts:
        prompts = [l.strip() for l in Path(args.prompts).read_text(encoding="utf-8").splitlines() if l.strip()]
    else:
        prompts = DEFAULT_PROMPTS
    prompts = prompts[: args.max]

    env = _load_env()
    api_key = env.get("LLM_API_KEY") or os.getenv("LLM_API_KEY")
    base_url = env.get("LLM_BASE_URL", "https://api.deepseek.com/v1")
    ds_model = "deepseek-chat"

    if not api_key or api_key == "please_fill_in":
        raise SystemExit("LLM_API_KEY not set in backend/.env")
    ds_client = OpenAI(api_key=api_key, base_url=base_url)

    have_ft = MERGED.exists()
    if not have_ft:
        print(f"WARNING: {MERGED} not found, will skip fine-tuned column")

    # Strategy: avoid loading 2 models in 8GB VRAM at once.
    # Round 1: load base, ask base + DeepSeek for all prompts, free.
    # Round 2: load FT, ask FT for all prompts, free.

    print(f"\n=== Round 1/2: BASE + DeepSeek ===")
    print(f"Loading BASE Qwen3-1.7B from {BASE} ...")
    base_tok = AutoTokenizer.from_pretrained(str(BASE), trust_remote_code=True)
    base_model = AutoModelForCausalLM.from_pretrained(
        str(BASE), torch_dtype=torch.bfloat16, device_map="auto", trust_remote_code=True,
    )
    base_model.eval()

    base_ans_list, base_t_list = [], []
    ds_ans_list, ds_t_list = [], []
    for i, q in enumerate(prompts, 1):
        print(f"  [{i}/{len(prompts)}] {q[:50]}...")
        a, t = _ask_deepseek(ds_client, ds_model, q)
        ds_ans_list.append(a); ds_t_list.append(t)
        a, t = _ask_local(base_model, base_tok, q)
        base_ans_list.append(a); base_t_list.append(t)
    _free(base_model)

    ft_ans_list, ft_t_list = [], []
    if have_ft:
        print(f"\n=== Round 2/2: FINE-TUNED ===")
        print(f"Loading FT model from {MERGED} ...")
        ft_tok = AutoTokenizer.from_pretrained(str(MERGED), trust_remote_code=True)
        ft_model = AutoModelForCausalLM.from_pretrained(
            str(MERGED), torch_dtype=torch.bfloat16, device_map="auto", trust_remote_code=True,
        )
        ft_model.eval()
        for i, q in enumerate(prompts, 1):
            print(f"  [{i}/{len(prompts)}] {q[:50]}...")
            a, t = _ask_local(ft_model, ft_tok, q)
            ft_ans_list.append(a); ft_t_list.append(t)
        _free(ft_model)
    else:
        ft_ans_list = ["(not built)"] * len(prompts)
        ft_t_list = [0.0] * len(prompts)

    out = ["# Model Comparison — DeepSeek-Chat vs Qwen3-1.7B (base) vs Qwen3-1.7B-Finance (LoRA)\n"]
    for i, q in enumerate(prompts, 1):
        out.append(f"\n## Q{i}: {q}\n")
        out.append(f"### DeepSeek-Chat (cloud, ~671B MoE) — {ds_t_list[i-1]:.2f}s\n\n{ds_ans_list[i-1]}\n")
        out.append(f"### Qwen3-1.7B Base (no fine-tune) — {base_t_list[i-1]:.2f}s\n\n{base_ans_list[i-1]}\n")
        out.append(f"### Qwen3-1.7B-Finance (our LoRA) — {ft_t_list[i-1]:.2f}s\n\n{ft_ans_list[i-1]}\n")
        out.append("\n---\n")

    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUT_FILE.write_text("\n".join(out), encoding="utf-8")
    print(f"\nReport saved → {OUT_FILE}")


if __name__ == "__main__":
    main()
