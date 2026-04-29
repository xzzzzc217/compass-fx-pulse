"""TimeXer-MS (multi-in, single-out) per-pair training with derived exogenous features.

This matches the original 花旗杯 design intent (`features=MS, enc_in=3, c_out=1`)
that the team's reference shell script described, but couldn't realise because
the news-scoring pipeline never produced exogenous time-series.

Instead of news scores, we use **technically derived exogenous features**:
  - realized volatility (20-day rolling std of log returns)  ← VIX-like signal
  - 5-day momentum (rate / rate.shift(5) - 1)                 ← trend signal

For each target pair USD/X, the model sees:
    enc_in = [rate, vol, mom]   →   c_out = [rate]

Saves 5 separate checkpoints (one per pair), runs backtest at the end.

Run:
    python -m llm.timexer.train_fx_ms                # train + backtest all 5 pairs
    python -m llm.timexer.train_fx_ms --pair USD_EUR # just one
"""
from __future__ import annotations

import os
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")

import argparse
import json
import sys
import warnings
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional

warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, Dataset

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from models.TimeXer import Model as TimeXerModel  # noqa: E402

PROJECT_ROOT = ROOT.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

LONG_CSV = ROOT / "data" / "fx_long.csv"
CKPT_DIR = ROOT / "checkpoints_ms"

PAIRS = ["USD_EUR", "USD_GBP", "USD_JPY", "USD_HKD", "USD_AUD"]


# ----------------------- Feature engineering -----------------------
from .feature_builder import build as build_pair_features  # noqa: E402


def build_features(rates: pd.Series, pair_name: Optional[str] = None) -> pd.DataFrame:
    """Build feature matrix for the target pair.

    Default mode: 11 features matching original 花旗杯 design (rate target last).
    See feature_builder.build() for details.
    """
    if pair_name:
        return build_pair_features(pair_name)

    # Fallback: minimal vol+mom feature set (used when running without macro CSVs)
    log_ret = np.log(rates).diff()
    vol = log_ret.rolling(20).std()
    mom = rates.pct_change(5)
    df = pd.DataFrame({"vol": vol, "mom": mom, "rate": rates})
    return df.dropna().astype(np.float32)


@dataclass
class TimeXerMSArgs:
    task_name: str = "long_term_forecast"
    seq_len: int = 60
    label_len: int = 30
    pred_len: int = 30
    enc_in: int = 3      # rate + vol + mom
    dec_in: int = 3
    c_out: int = 1       # predict ONLY the rate
    d_model: int = 128
    n_heads: int = 4
    e_layers: int = 2
    d_ff: int = 256
    dropout: float = 0.1
    activation: str = "gelu"
    factor: int = 1
    embed: str = "timeF"
    freq: str = "d"
    use_norm: int = 1
    patch_len: int = 12
    features: str = "MS"
    output_attention: bool = False


class FXMSDataset(Dataset):
    def __init__(self, X: np.ndarray, seq_len: int, pred_len: int):
        self.X = X.astype(np.float32)  # (T, 3)
        self.seq_len, self.pred_len = seq_len, pred_len

    def __len__(self) -> int:
        return max(0, len(self.X) - self.seq_len - self.pred_len + 1)

    def __getitem__(self, i: int):
        x = self.X[i: i + self.seq_len]                                # (seq, 3)
        # Target = rate column (index -1) of the future window, shape (pred, 1)
        y = self.X[i + self.seq_len: i + self.seq_len + self.pred_len, -1:]
        x_mark = np.zeros((self.seq_len, 4), dtype=np.float32)
        y_mark = np.zeros((self.pred_len, 4), dtype=np.float32)
        return x, x_mark, y, y_mark


# ----------------------- Train one pair -----------------------
def train_one(pair: str, args) -> dict:
    print(f"\n{'='*70}\n=== Training MS model for {pair} ===\n{'='*70}")

    if args.full_features:
        feats = build_pair_features(pair, mode=args.feature_mode)
    else:
        df_full = pd.read_csv(LONG_CSV, parse_dates=["date"]).set_index("date")
        rates = df_full[pair].astype(np.float32)
        feats = build_features(rates)
    X = feats.values
    print(f"  features ({X.shape[1]}): {feats.columns.tolist()}")
    print(f"  shape={X.shape}, range {feats.index.min().date()} → {feats.index.max().date()}")

    n = len(X)
    n_tr = int(n * 0.70)
    n_va = int(n * 0.15)
    X_tr, X_va, X_te = X[:n_tr], X[n_tr: n_tr + n_va], X[n_tr + n_va:]

    mean = X_tr.mean(axis=0, keepdims=True)
    std = X_tr.std(axis=0, keepdims=True) + 1e-6
    X_tr_n = (X_tr - mean) / std
    X_va_n = (X_va - mean) / std
    X_te_n = (X_te - mean) / std

    n_feat = X.shape[1]
    cfg = TimeXerMSArgs(
        seq_len=args.seq_len, pred_len=args.pred_len, label_len=args.pred_len,
        enc_in=n_feat, dec_in=n_feat,  # adapt to feature count
        d_model=args.d_model, n_heads=args.n_heads, e_layers=args.e_layers,
        d_ff=args.d_ff, patch_len=args.patch_len,
    )
    train_ds = FXMSDataset(X_tr_n, cfg.seq_len, cfg.pred_len)
    val_ds = FXMSDataset(X_va_n, cfg.seq_len, cfg.pred_len)
    print(f"  windows: train={len(train_ds)}  val={len(val_ds)}")

    train_loader = DataLoader(train_ds, batch_size=args.batch_size, shuffle=True)
    val_loader = DataLoader(val_ds, batch_size=args.batch_size, shuffle=False)

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = TimeXerModel(cfg).to(device)
    print(f"  params: {sum(p.numel() for p in model.parameters() if p.requires_grad)/1e6:.2f}M  device={device}")

    optim = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=1e-4)
    sched = torch.optim.lr_scheduler.CosineAnnealingLR(optim, T_max=args.epochs)
    loss_fn = nn.MSELoss()

    best = float("inf")
    CKPT_DIR.mkdir(parents=True, exist_ok=True)
    ckpt_path = CKPT_DIR / f"{pair}.pt"
    meta_path = CKPT_DIR / f"{pair}.meta.json"

    # Decoder input has SAME channels as encoder input (enc_in=3); the model's
    # output is also (batch, pred_len, enc_in). We compute loss only against
    # the LAST channel (= the rate target), per TimeXer MS convention.
    def _take_target(out_t: torch.Tensor) -> torch.Tensor:
        return out_t[..., -1:]  # keep dim, shape (batch, pred_len, 1)

    for ep in range(1, args.epochs + 1):
        model.train()
        tl = 0.0; nb = 0
        for x, xm, y, ym in train_loader:
            x, xm, y, ym = (t.to(device) for t in (x, xm, y, ym))
            # Decoder input must mirror encoder dim (3 channels); fill last
            # channel with zeros (target prefix), other channels with x's tail.
            dec_inp = torch.zeros(x.shape[0], cfg.pred_len, cfg.enc_in, device=device)
            optim.zero_grad()
            out = model(x, xm, dec_inp, ym)
            loss = loss_fn(_take_target(out), y)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optim.step()
            tl += loss.item(); nb += 1
        tl /= max(1, nb)

        model.eval()
        vl = 0.0; nv = 0
        with torch.no_grad():
            for x, xm, y, ym in val_loader:
                x, xm, y, ym = (t.to(device) for t in (x, xm, y, ym))
                dec_inp = torch.zeros(x.shape[0], cfg.pred_len, cfg.enc_in, device=device)
                out = model(x, xm, dec_inp, ym)
                vl += loss_fn(_take_target(out), y).item(); nv += 1
        vl /= max(1, nv)
        sched.step()

        marker = ""
        if vl < best:
            best = vl
            torch.save(model.state_dict(), ckpt_path)
            meta_path.write_text(json.dumps({
                "config": asdict(cfg),
                "pair": pair,
                "feature_cols": feats.columns.tolist(),
                "mean": mean.flatten().tolist(),
                "std": std.flatten().tolist(),
                "best_val": best,
                "epoch": ep,
            }, indent=2), encoding="utf-8")
            marker = "  [saved]"
        print(f"    ep {ep:3d}/{args.epochs}  train={tl:.4f}  val={vl:.4f}{marker}")

    return {"pair": pair, "best_val": best,
            "ckpt": str(ckpt_path), "meta": str(meta_path)}


# ----------------------- Backtest one pair -----------------------
def backtest_one(pair: str, n_anchors: int = 60) -> dict:
    """Rolling-origin backtest of TimeXer-MS vs ARIMA on this pair."""
    from statsmodels.tsa.statespace.sarimax import SARIMAX

    meta_path = CKPT_DIR / f"{pair}.meta.json"
    ckpt_path = CKPT_DIR / f"{pair}.pt"
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    cfg = TimeXerMSArgs(**{k: v for k, v in meta["config"].items()
                           if k in TimeXerMSArgs.__dataclass_fields__})
    # mean/std were flatten()'d when saved; restore as 1D vectors of length 3
    mean_flat = np.array(meta["mean"], dtype=np.float32)
    std_flat = np.array(meta["std"], dtype=np.float32)
    # rate is now the LAST column [vol, mom, rate]
    rate_mean = float(mean_flat[-1])
    rate_std = float(std_flat[-1])

    if cfg.enc_in > 3:
        # Try modes in order until enc_in matches what was trained with
        for m in ("v3", "v2", "v1"):
            try:
                feats = build_pair_features(pair, mode=m)
                if feats.shape[1] == cfg.enc_in:
                    break
            except Exception:
                pass
        else:
            feats = build_pair_features(pair, mode="v3")
    else:
        df_full = pd.read_csv(LONG_CSV, parse_dates=["date"]).set_index("date")
        rates = df_full[pair].astype(np.float32)
        feats = build_features(rates)
    X = feats.values
    rate_col = feats["rate"].values

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = TimeXerModel(cfg).to(device)
    model.load_state_dict(torch.load(ckpt_path, map_location=device))
    model.eval()

    n = len(X)
    last = n - cfg.pred_len
    first = max(cfg.seq_len, last - n_anchors)
    anchors = list(range(first, last))

    tx_errs, ar_errs = [], []
    for a in anchors:
        truth = rate_col[a: a + cfg.pred_len]

        # ---- TimeXer-MS prediction ----
        x_window = X[a - cfg.seq_len: a]
        x_n = (x_window - mean_flat) / std_flat
        x_t = torch.from_numpy(x_n).unsqueeze(0).to(device)
        x_mark = torch.zeros(1, cfg.seq_len, 4, device=device)
        y_mark = torch.zeros(1, cfg.pred_len, 4, device=device)
        # decoder input mirrors encoder dim (3 channels)
        dec_inp = torch.zeros(1, cfg.pred_len, cfg.enc_in, device=device)
        with torch.no_grad():
            out = model(x_t, x_mark, dec_inp, y_mark)
        # take only the LAST channel (target = rate)
        pred_n = out[0, :, -1].cpu().numpy()
        tx_pred = pred_n * rate_std + rate_mean
        tx_errs.append(float(np.mean(np.abs(tx_pred - truth))))

        # ---- ARIMA(1,1,1) baseline ----
        try:
            m = SARIMAX(rate_col[:a], order=(1, 1, 1),
                        enforce_stationarity=False, enforce_invertibility=False)
            f = m.fit(disp=False, maxiter=80)
            ar_pred = np.asarray(f.forecast(steps=cfg.pred_len).values)
        except Exception:
            ar_pred = np.full(cfg.pred_len, rate_col[a - 1])
        ar_errs.append(np.mean(np.abs(ar_pred - truth)))

    tx_mae = float(np.mean(tx_errs))
    ar_mae = float(np.mean(ar_errs))
    imp = (ar_mae - tx_mae) / ar_mae * 100 if ar_mae > 0 else 0
    return {"pair": pair, "timexer_mae": tx_mae, "arima_mae": ar_mae,
            "improvement_pct": imp}


# ----------------------- Main -----------------------
def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--epochs", type=int, default=20)
    p.add_argument("--batch_size", type=int, default=64)
    p.add_argument("--lr", type=float, default=5e-4)
    p.add_argument("--seq_len", type=int, default=60)
    p.add_argument("--pred_len", type=int, default=30)
    p.add_argument("--d_model", type=int, default=128)
    p.add_argument("--n_heads", type=int, default=4)
    p.add_argument("--e_layers", type=int, default=2)
    p.add_argument("--d_ff", type=int, default=256)
    p.add_argument("--patch_len", type=int, default=12)
    p.add_argument("--n_anchors", type=int, default=60)
    p.add_argument("--pair", type=str, default=None,
                   help="Only train this pair; default: all 5")
    p.add_argument("--skip-train", action="store_true")
    p.add_argument("--full-features", action="store_true",
                   help="Use full feature set (default v3 hybrid)")
    p.add_argument("--feature-mode", default="v3", choices=["v1", "v2", "v3"],
                   help="v1=11 raw incl yearly macro, v2=9 daily+cyclic, v3=4 hybrid (vol+mom+vix+dxy)")
    args = p.parse_args()

    pairs = [args.pair] if args.pair else PAIRS

    if not args.skip_train:
        for pair in pairs:
            train_one(pair, args)

    print("\n" + "=" * 70)
    print("=== Backtest summary ===")
    print("=" * 70)
    print(f"{'Pair':<10} {'TimeXer-MS MAE':>16} {'ARIMA MAE':>14} {'Improvement':>14}")
    print("-" * 70)
    results = []
    for pair in pairs:
        try:
            r = backtest_one(pair, n_anchors=args.n_anchors)
            results.append(r)
            print(f"{pair:<10} {r['timexer_mae']:>16.4f} {r['arima_mae']:>14.4f} "
                  f"{r['improvement_pct']:>13.2f}%")
        except Exception as exc:
            print(f"{pair:<10} backtest failed: {exc}")

    if results:
        all_tx = [r["timexer_mae"] for r in results]
        all_ar = [r["arima_mae"] for r in results]
        # Note: cross-pair averaging is misleading (different scales).
        # Report per-pair numbers as the result.
        print("-" * 70)
        # Macro-average percentage (each pair counts equally)
        mean_imp = float(np.mean([r["improvement_pct"] for r in results]))
        print(f"Macro-avg improvement (each pair weighted equally): {mean_imp:.2f}%")

    out = Path("D:/temp_resume/backtest_ms.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"\nResults saved: {out}")


if __name__ == "__main__":
    main()
