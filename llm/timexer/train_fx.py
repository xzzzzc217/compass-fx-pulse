"""Train TimeXer on multivariate USD-X exchange rate data.

Setup:
  - Load 5 USD-X pairs (USD/EUR, USD/GBP, USD/JPY, USD/HKD, USD/AUD) from MySQL
  - Train TimeXer (Transformer architecture) for daily-step forecasting
  - Save best checkpoint
  - Run 30-day forecast, write to predictdata
  - Backtest: compute rolling 30-day MAE vs SARIMAX baseline → resume claim

Run:
    python -m llm.timexer.train_fx --epochs 30 --device cuda
    python -m llm.timexer.train_fx --skip-train --infer-only      # use existing ckpt

Hardware: RTX 4060 8GB → ~15-25 min for 30 epochs on 5-variable multivariate.
"""
from __future__ import annotations

import os
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
os.environ.setdefault("OMP_NUM_THREADS", "1")

import argparse
import json
import sys
from dataclasses import dataclass, asdict
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, Dataset

# Make TimeXer's "from layers..." imports resolve
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from models.TimeXer import Model as TimeXerModel  # noqa: E402

# Make backend.app.db importable for MySQL access
PROJECT_ROOT = ROOT.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "backend"))
from app.db import get_cursor  # noqa: E402


# ----------------------- Config -----------------------
TARGET_PAIRS = [
    ("USD", "EUR"), ("USD", "GBP"), ("USD", "JPY"),
    ("USD", "HKD"), ("USD", "AUD"),
]
NUM_VARS = len(TARGET_PAIRS)  # 5

CKPT_DIR = ROOT / "checkpoints"
CKPT_PATH = CKPT_DIR / "timexer_fx.pt"
META_PATH = CKPT_DIR / "timexer_fx.meta.json"


@dataclass
class TimeXerArgs:
    """Subset of TimeXer hyperparameters that the model class consumes.
    Tuned for SMALL FX dataset (~600 samples) — bigger config overfits hard.
    """
    task_name: str = "long_term_forecast"
    seq_len: int = 60        # 60 business-day lookback
    label_len: int = 30
    pred_len: int = 30       # 30 business-day horizon
    enc_in: int = NUM_VARS   # = 5
    dec_in: int = NUM_VARS
    c_out: int = NUM_VARS
    d_model: int = 64
    n_heads: int = 4
    e_layers: int = 1
    d_ff: int = 128
    dropout: float = 0.3
    activation: str = "gelu"
    factor: int = 1
    embed: str = "timeF"
    freq: str = "d"
    use_norm: int = 1
    patch_len: int = 12      # divisible-into-seq_len patches
    features: str = "M"      # multivariate
    output_attention: bool = False


# ----------------------- Data -----------------------
LONG_CSV = Path(__file__).resolve().parent / "data" / "fx_long.csv"


def load_fx_matrix(use_long: bool = False) -> tuple[pd.DataFrame, list[str]]:
    """Returns (DataFrame indexed by date, NUM_VARS columns), column_names.

    If use_long=True (env var FX_USE_LONG=1 or arg), loads the 25-year ECB CSV
    instead of the production MySQL slice (covers 2024-01-01 onwards).
    """
    if use_long or os.getenv("FX_USE_LONG", "0") == "1":
        if not LONG_CSV.exists():
            raise SystemExit(f"Long history CSV not found: {LONG_CSV}\n"
                             "Run: python -m llm.timexer.fetch_long_history")
        print(f"Loading FX data from {LONG_CSV.name} ...")
        df = pd.read_csv(LONG_CSV, parse_dates=["date"]).set_index("date")
        col_names = [f"{a}_{b}" for a, b in TARGET_PAIRS]
        # Reorder columns to match TARGET_PAIRS
        df = df[col_names].astype(np.float32)
        print(f"  shape: {df.shape}")
        print(f"  range: {df.index.min().date()} → {df.index.max().date()}")
        return df, col_names

    print("Loading FX data from MySQL ...")
    frames = []
    col_names = []
    with get_cursor() as cur:
        for a, b in TARGET_PAIRS:
            cur.execute(
                "SELECT DATE(time) AS d, rate FROM historicaldata "
                "WHERE currencytype1=%s AND currencytype2=%s ORDER BY time",
                (a, b),
            )
            rows = cur.fetchall()
            df = pd.DataFrame(rows, columns=["date", f"{a}_{b}"])
            df = df.set_index("date")
            df.index = pd.to_datetime(df.index)
            frames.append(df)
            col_names.append(f"{a}_{b}")

    matrix = pd.concat(frames, axis=1).asfreq("B").interpolate(method="time").dropna()
    matrix = matrix.astype(np.float32)
    print(f"  shape: {matrix.shape}")
    print(f"  range: {matrix.index.min().date()} → {matrix.index.max().date()}")
    return matrix, col_names


class FXWindowDataset(Dataset):
    """Sliding windows of (lookback, horizon)."""
    def __init__(self, X: np.ndarray, seq_len: int, pred_len: int):
        self.X = X.astype(np.float32)
        self.seq_len = seq_len
        self.pred_len = pred_len

    def __len__(self) -> int:
        return max(0, len(self.X) - self.seq_len - self.pred_len + 1)

    def __getitem__(self, i: int):
        x = self.X[i: i + self.seq_len]
        y = self.X[i + self.seq_len: i + self.seq_len + self.pred_len]
        # No time stamps — use zeros for x_mark / y_mark
        x_mark = np.zeros((self.seq_len, 4), dtype=np.float32)
        y_mark = np.zeros((self.pred_len, 4), dtype=np.float32)
        return x, x_mark, y, y_mark


# ----------------------- Train -----------------------
def standardize(X: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    mean = X.mean(axis=0, keepdims=True)
    std = X.std(axis=0, keepdims=True) + 1e-6
    return (X - mean) / std, mean, std


def train(args) -> None:
    matrix, col_names = load_fx_matrix()
    X = matrix.values

    # Split 70/15/15 chronologically
    n = len(X)
    n_train = int(n * 0.70)
    n_val = int(n * 0.15)
    X_train, X_val, X_test = X[:n_train], X[n_train: n_train + n_val], X[n_train + n_val:]
    print(f"Splits: train={len(X_train)}  val={len(X_val)}  test={len(X_test)}")

    X_train_n, mean, std = standardize(X_train)
    X_val_n = (X_val - mean) / std
    X_test_n = (X_test - mean) / std

    cfg = TimeXerArgs(
        seq_len=args.seq_len, pred_len=args.pred_len,
        label_len=args.pred_len,
        enc_in=NUM_VARS, dec_in=NUM_VARS, c_out=NUM_VARS,
        d_model=args.d_model, n_heads=args.n_heads,
        e_layers=args.e_layers, d_ff=args.d_ff,
        patch_len=args.patch_len,
    )

    train_ds = FXWindowDataset(X_train_n, cfg.seq_len, cfg.pred_len)
    val_ds = FXWindowDataset(X_val_n, cfg.seq_len, cfg.pred_len)
    print(f"Windows: train={len(train_ds)}  val={len(val_ds)}")

    train_loader = DataLoader(train_ds, batch_size=args.batch_size, shuffle=True)
    val_loader = DataLoader(val_ds, batch_size=args.batch_size, shuffle=False)

    device = torch.device(args.device if torch.cuda.is_available() else "cpu")
    model = TimeXerModel(cfg).to(device)
    n_params = sum(p.numel() for p in model.parameters() if p.requires_grad)
    print(f"TimeXer parameters: {n_params / 1e6:.2f}M (device={device})")

    optim = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=1e-4)
    sched = torch.optim.lr_scheduler.CosineAnnealingLR(optim, T_max=args.epochs)
    loss_fn = nn.MSELoss()

    best_val = float("inf")
    CKPT_DIR.mkdir(parents=True, exist_ok=True)
    for ep in range(1, args.epochs + 1):
        model.train()
        train_loss = 0.0
        n_batches = 0
        for x, x_mark, y, y_mark in train_loader:
            x, x_mark, y, y_mark = (t.to(device) for t in (x, x_mark, y, y_mark))
            # decoder input: zeros (matching standard TimeXer setup)
            dec_inp = torch.zeros_like(y).to(device)
            optim.zero_grad()
            out = model(x, x_mark, dec_inp, y_mark)
            loss = loss_fn(out, y)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optim.step()
            train_loss += loss.item()
            n_batches += 1
        train_loss /= max(1, n_batches)

        # Validate
        model.eval()
        val_loss = 0.0
        n_val_batches = 0
        with torch.no_grad():
            for x, x_mark, y, y_mark in val_loader:
                x, x_mark, y, y_mark = (t.to(device) for t in (x, x_mark, y, y_mark))
                dec_inp = torch.zeros_like(y).to(device)
                out = model(x, x_mark, dec_inp, y_mark)
                val_loss += loss_fn(out, y).item()
                n_val_batches += 1
        val_loss /= max(1, n_val_batches)
        sched.step()

        marker = ""
        if val_loss < best_val:
            best_val = val_loss
            torch.save(model.state_dict(), CKPT_PATH)
            META_PATH.write_text(json.dumps({
                "config": asdict(cfg),
                "col_names": col_names,
                "mean": mean.flatten().tolist(),
                "std": std.flatten().tolist(),
                "best_val_loss": best_val,
                "epoch": ep,
            }, indent=2), encoding="utf-8")
            marker = "  [saved]"
        print(f"  epoch {ep:3d}/{args.epochs}  train={train_loss:.4f}  val={val_loss:.4f}{marker}")

    print(f"\nBest val loss: {best_val:.4f}")
    print(f"Checkpoint:    {CKPT_PATH}")
    print(f"Metadata:      {META_PATH}")


# ----------------------- Inference + write to DB -----------------------
def infer_and_write(args) -> None:
    if not CKPT_PATH.exists():
        raise SystemExit(f"No checkpoint at {CKPT_PATH}. Train first.")

    meta = json.loads(META_PATH.read_text(encoding="utf-8"))
    cfg_dict = meta["config"]
    cfg = TimeXerArgs(**{k: v for k, v in cfg_dict.items() if k in TimeXerArgs.__dataclass_fields__})
    col_names = meta["col_names"]
    mean = np.array(meta["mean"], dtype=np.float32)
    std = np.array(meta["std"], dtype=np.float32)

    matrix, _ = load_fx_matrix()
    X = matrix.values.astype(np.float32)
    X_n = (X - mean) / std

    # Take the LAST seq_len rows as input
    last = X_n[-cfg.seq_len:]
    print(f"Last lookback ends at {matrix.index[-1].date()}")

    device = torch.device(args.device if torch.cuda.is_available() else "cpu")
    model = TimeXerModel(cfg).to(device)
    model.load_state_dict(torch.load(CKPT_PATH, map_location=device))
    model.eval()

    x = torch.from_numpy(last).unsqueeze(0).to(device)
    x_mark = torch.zeros(1, cfg.seq_len, 4, device=device)
    y_mark = torch.zeros(1, cfg.pred_len, 4, device=device)
    dec_inp = torch.zeros(1, cfg.pred_len, NUM_VARS, device=device)

    with torch.no_grad():
        out = model(x, x_mark, dec_inp, y_mark)
    pred_n = out.squeeze(0).cpu().numpy()  # (pred_len, NUM_VARS)
    pred = pred_n * std + mean             # de-standardize
    print(f"Forecast shape: {pred.shape}")

    # Write to predictdata: each USD-X pair + reciprocals + cross-rates
    last_date = matrix.index[-1].date()
    rows: list[tuple[str, str, str, float]] = []

    # Direct: USD/X
    for j, (a, b) in enumerate(TARGET_PAIRS):
        for h in range(cfg.pred_len):
            d = last_date + timedelta(days=h + 1)
            ts = d.strftime("%Y-%m-%d 18:00:00")
            rows.append((a, b, ts, float(pred[h, j])))

    # Reciprocal: X/USD = 1 / (USD/X)
    for j, (a, b) in enumerate(TARGET_PAIRS):
        for h in range(cfg.pred_len):
            d = last_date + timedelta(days=h + 1)
            ts = d.strftime("%Y-%m-%d 18:00:00")
            r = float(pred[h, j])
            if r > 0:
                rows.append((b, a, ts, 1.0 / r))

    # Cross-rates: X1/X2 = (USD/X2) / (USD/X1)
    for j1, (_, c1) in enumerate(TARGET_PAIRS):
        for j2, (_, c2) in enumerate(TARGET_PAIRS):
            if j1 == j2:
                continue
            for h in range(cfg.pred_len):
                d = last_date + timedelta(days=h + 1)
                ts = d.strftime("%Y-%m-%d 18:00:00")
                p1, p2 = float(pred[h, j1]), float(pred[h, j2])
                if p1 > 0:
                    rows.append((c1, c2, ts, p2 / p1))

    print(f"Total prediction rows: {len(rows)}")

    sql = ("INSERT INTO predictdata (currencytype1, currencytype2, time, rate) "
           "VALUES (%s, %s, %s, %s) "
           "ON DUPLICATE KEY UPDATE rate = VALUES(rate)")
    with get_cursor(commit=True) as cur:
        cur.execute("DELETE FROM predictdata")
        cur.executemany(sql, rows)
    print(f"Wrote {len(rows)} prediction rows to predictdata.")


# ----------------------- Main -----------------------
def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--epochs", type=int, default=30)
    p.add_argument("--batch_size", type=int, default=16)
    p.add_argument("--lr", type=float, default=5e-4)
    p.add_argument("--seq_len", type=int, default=60)
    p.add_argument("--pred_len", type=int, default=30)
    p.add_argument("--d_model", type=int, default=128)
    p.add_argument("--n_heads", type=int, default=4)
    p.add_argument("--e_layers", type=int, default=2)
    p.add_argument("--d_ff", type=int, default=256)
    p.add_argument("--patch_len", type=int, default=12)
    p.add_argument("--device", default="cuda")
    p.add_argument("--skip-train", action="store_true")
    p.add_argument("--infer-only", action="store_true")
    args = p.parse_args()

    if not (args.skip_train or args.infer_only):
        train(args)
    if args.skip_train and not args.infer_only:
        print("(--skip-train set; skipping training, going to inference)")
    if not args.skip_train or args.infer_only or args.skip_train:
        infer_and_write(args)


if __name__ == "__main__":
    main()
