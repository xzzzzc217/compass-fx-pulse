"""LoRA SFT for Qwen3-1.7B on the CompassFX finance dataset.

Hardware target: single RTX 4060 Laptop GPU (8 GB VRAM, sm_89, BF16-capable).
Memory budget:
    - 4-bit NF4 base weights:  ~1.2 GB
    - LoRA adapters (r=16):    ~14 MB
    - Activations + grads:     ~3-4 GB (with grad checkpointing)
    - Optimizer (paged AdamW): ~0.5 GB
    Total peak: ~5-6 GB → leaves ~2 GB headroom
Wall time estimate: ~2-3 hours for 3 epochs over ~3200 examples.

Usage:
    python training/train_lora.py
    python training/train_lora.py --epochs 5 --batch_size 2

Outputs:
    output/lora-qwen3-1.7b/checkpoint-XXX/
    output/lora-qwen3-1.7b/final/   (best adapter)
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path

import torch
from datasets import load_dataset
from peft import LoraConfig, prepare_model_for_kbit_training
from transformers import (
    AutoModelForCausalLM,
    AutoTokenizer,
    BitsAndBytesConfig,
)
from trl import SFTConfig, SFTTrainer

# Reproducibility
SEED = 42
torch.manual_seed(SEED)
torch.cuda.manual_seed_all(SEED)

ROOT = Path(__file__).resolve().parent.parent  # llm/
MODEL_DIR = ROOT / "models" / "Qwen3-1.7B"
DATA_DIR = ROOT / "data"
OUTPUT_DIR = ROOT / "output" / "lora-qwen3-1.7b"


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--epochs", type=int, default=2,
                   help="2 epochs is sweet spot for 3K LoRA SFT (3 risks zh overfit)")
    p.add_argument("--batch_size", type=int, default=2,
                   help="Per-device train batch size; effective = bs * grad_accum")
    p.add_argument("--grad_accum", type=int, default=8)
    p.add_argument("--lr", type=float, default=2e-4)
    p.add_argument("--lora_r", type=int, default=16)
    p.add_argument("--lora_alpha", type=int, default=32)
    p.add_argument("--max_seq_len", type=int, default=512,
                   help="512 covers ~95% of our finance Q&A; cuts attention compute 4x")
    p.add_argument("--save_total_limit", type=int, default=2)
    p.add_argument("--logging_steps", type=int, default=10)
    p.add_argument("--warmup_ratio", type=float, default=0.05)
    p.add_argument("--weight_decay", type=float, default=0.01)
    p.add_argument("--eval_steps", type=int, default=100)
    p.add_argument("--quant", choices=["bf16", "4bit"], default="bf16",
                   help="bf16 is ~3x faster than 4-bit on 8GB; falls back to 4-bit if OOM")
    p.add_argument("--grad_ckpt", action="store_true",
                   help="enable gradient checkpointing (slower but lower VRAM, "
                        "needed for batch_size>=4 on 8GB)")
    p.add_argument("--no_grad_ckpt", action="store_true",
                   help="(deprecated: grad_ckpt is now off by default)")
    p.add_argument("--smoke", action="store_true",
                   help="run 1 train step only, then exit (sanity check)")
    return p.parse_args()


def main() -> None:
    args = parse_args()

    if not MODEL_DIR.exists():
        raise SystemExit(
            f"Model dir not found: {MODEL_DIR}\n"
            "Run scripts/download_model.py first."
        )
    train_file = DATA_DIR / "train.jsonl"
    eval_file = DATA_DIR / "eval.jsonl"
    if not train_file.exists() or not eval_file.exists():
        raise SystemExit(
            f"Dataset not found.\nRun scripts/prepare_dataset.py first.\n"
            f"  expected: {train_file}\n  expected: {eval_file}"
        )

    print("=" * 60)
    print("LoRA SFT — Qwen3-1.7B on CompassFX finance corpus")
    print("=" * 60)
    print(f"Model:        {MODEL_DIR}")
    print(f"Train data:   {train_file}")
    print(f"Eval data:    {eval_file}")
    print(f"Output:       {OUTPUT_DIR}")
    print(f"Epochs:       {args.epochs}")
    print(f"Batch size:   {args.batch_size} × {args.grad_accum} = "
          f"effective {args.batch_size * args.grad_accum}")
    print(f"LR:           {args.lr}")
    print(f"LoRA r:       {args.lora_r} (alpha={args.lora_alpha})")
    print(f"Max seq len:  {args.max_seq_len}")
    print()

    # --- Quantization (optional) ---
    bnb_config = None
    if args.quant == "4bit":
        bnb_config = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_use_double_quant=True,
            bnb_4bit_compute_dtype=torch.bfloat16,
        )

    # --- Tokenizer ---
    print("[1/5] Loading tokenizer ...")
    tokenizer = AutoTokenizer.from_pretrained(
        str(MODEL_DIR),
        trust_remote_code=True,
        use_fast=True,
    )
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
    tokenizer.padding_side = "right"  # SFTTrainer expects right padding

    # --- Base model ---
    print(f"[2/5] Loading base model ({args.quant}) ...")
    model_kwargs = dict(
        device_map={"": 0},
        trust_remote_code=True,
        torch_dtype=torch.bfloat16,
    )
    if bnb_config is not None:
        model_kwargs["quantization_config"] = bnb_config
    model = AutoModelForCausalLM.from_pretrained(str(MODEL_DIR), **model_kwargs)
    model.config.use_cache = False  # incompatible with grad checkpointing
    # New default: grad_ckpt OFF (faster). Pass --grad_ckpt to enable for OOM cases.
    use_ckpt = args.grad_ckpt
    if bnb_config is not None:
        model = prepare_model_for_kbit_training(
            model, use_gradient_checkpointing=use_ckpt
        )
    elif use_ckpt:
        model.gradient_checkpointing_enable(gradient_checkpointing_kwargs={"use_reentrant": False})
        if hasattr(model, "enable_input_require_grads"):
            model.enable_input_require_grads()

    # --- LoRA config ---
    # Target the linear layers in attention + MLP (Qwen3 uses standard names)
    lora_config = LoraConfig(
        r=args.lora_r,
        lora_alpha=args.lora_alpha,
        lora_dropout=0.05,
        bias="none",
        task_type="CAUSAL_LM",
        target_modules=[
            "q_proj", "k_proj", "v_proj", "o_proj",
            "gate_proj", "up_proj", "down_proj",
        ],
    )

    # --- Datasets ---
    print("[3/5] Loading dataset ...")
    train_ds = load_dataset(
        "json", data_files=str(train_file), split="train"
    )
    eval_ds = load_dataset(
        "json", data_files=str(eval_file), split="train"
    )
    print(f"  train: {len(train_ds)} | eval: {len(eval_ds)}")

    # --- SFT config ---
    print("[4/5] Building trainer ...")
    sft_config = SFTConfig(
        output_dir=str(OUTPUT_DIR),
        max_steps=1 if args.smoke else -1,
        num_train_epochs=args.epochs,
        per_device_train_batch_size=args.batch_size,
        per_device_eval_batch_size=args.batch_size,
        gradient_accumulation_steps=args.grad_accum,
        learning_rate=args.lr,
        warmup_ratio=args.warmup_ratio,
        weight_decay=args.weight_decay,
        lr_scheduler_type="cosine",
        bf16=True,
        gradient_checkpointing=use_ckpt,
        gradient_checkpointing_kwargs={"use_reentrant": False} if use_ckpt else None,
        optim="paged_adamw_8bit",
        max_length=args.max_seq_len,
        packing=False,
        logging_steps=args.logging_steps,
        eval_strategy="steps",
        eval_steps=args.eval_steps,
        save_strategy="epoch",
        save_total_limit=args.save_total_limit,
        load_best_model_at_end=False,  # peft + load_best can be flaky
        report_to="none",  # set to "wandb" if you log in
        dataset_text_field=None,  # use messages format
        seed=SEED,
        data_seed=SEED,
    )

    trainer = SFTTrainer(
        model=model,
        args=sft_config,
        train_dataset=train_ds,
        eval_dataset=eval_ds,
        peft_config=lora_config,
        processing_class=tokenizer,
    )

    # Print trainable param summary
    trainable = sum(p.numel() for p in trainer.model.parameters() if p.requires_grad)
    total = sum(p.numel() for p in trainer.model.parameters())
    print(f"  trainable params: {trainable / 1e6:.2f}M / {total / 1e6:.2f}M "
          f"({100 * trainable / total:.2f}%)")

    # --- Train ---
    print()
    print("[5/5] Training ...")
    print("=" * 60)
    trainer.train()

    # --- Save final adapter ---
    final_dir = OUTPUT_DIR / "final"
    final_dir.mkdir(parents=True, exist_ok=True)
    trainer.save_model(str(final_dir))
    tokenizer.save_pretrained(str(final_dir))
    print(f"\nFinal adapter saved → {final_dir}")
    print("Next: python training/merge_lora.py  (to fold adapter into base for vLLM)")


if __name__ == "__main__":
    main()
