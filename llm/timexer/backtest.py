"""Rolling-origin backtest: TimeXer vs SARIMAX.

For each anchor date in the test window, use the preceding `seq_len` days to
predict the next `pred_len` days, then compare with the actual realised series.
Aggregates MAE per pair + overall, computes % improvement.

Run:
    python -m llm.timexer.backtest

Output: prints per-pair MAE table + saves D:/temp_resume/backtest.json
"""
from __future__ import annotations

import os
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
os.environ.setdefault("OMP_NUM_THREADS", "1")

import json
import sys
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd
import torch

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT.parent.parent / "backend"))

from models.TimeXer import Model as TimeXerModel  # noqa: E402
from train_fx import (  # noqa: E402
    load_fx_matrix, TARGET_PAIRS, NUM_VARS, TimeXerArgs, CKPT_PATH, META_PATH,
)


import argparse as _argparse
_p = _argparse.ArgumentParser()
_p.add_argument("--seq-len", type=int, default=60)
_p.add_argument("--pred-len", type=int, default=30)
_p.add_argument("--n-anchors", type=int, default=60)
_p.add_argument("--long", action="store_true",
                help="Use 25-year long-history CSV instead of production MySQL slice")
_args, _ = _p.parse_known_args()
SEQ_LEN = _args.seq_len
PRED_LEN = _args.pred_len
N_ANCHORS = _args.n_anchors
USE_LONG = _args.long or os.getenv("FX_USE_LONG", "0") == "1"


def arima_forecast(series: np.ndarray, horizon: int,
                   order=(1, 1, 1), seasonal=False) -> np.ndarray:
    """Plain ARIMA (or SARIMAX) baseline."""
    from statsmodels.tsa.statespace.sarimax import SARIMAX
    s = pd.Series(series)
    try:
        seasonal_order = (1, 0, 1, 5) if seasonal else (0, 0, 0, 0)
        model = SARIMAX(
            s, order=order, seasonal_order=seasonal_order,
            enforce_stationarity=False, enforce_invertibility=False,
        )
        fit = model.fit(disp=False, maxiter=80)
        return np.asarray(fit.forecast(steps=horizon).values, dtype=np.float32)
    except Exception:
        return np.full(horizon, float(s.iloc[-1]), dtype=np.float32)


def sarimax_forecast(series: np.ndarray, horizon: int) -> np.ndarray:
    return arima_forecast(series, horizon, order=(1, 1, 1), seasonal=True)


def main() -> None:
    matrix, col_names = load_fx_matrix(use_long=USE_LONG)
    X = matrix.values.astype(np.float32)
    n = len(X)
    print(f"Total samples: {n} | columns: {col_names}")

    # Load TimeXer
    meta = json.loads(META_PATH.read_text(encoding="utf-8"))
    cfg_dict = meta["config"]
    cfg = TimeXerArgs(**{k: v for k, v in cfg_dict.items()
                         if k in TimeXerArgs.__dataclass_fields__})
    mean = np.array(meta["mean"], dtype=np.float32)
    std = np.array(meta["std"], dtype=np.float32)

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = TimeXerModel(cfg).to(device)
    model.load_state_dict(torch.load(CKPT_PATH, map_location=device))
    model.eval()

    # Anchor positions: the last N_ANCHORS valid anchors before n - pred_len
    last_valid_anchor = n - PRED_LEN
    first_anchor = max(SEQ_LEN, last_valid_anchor - N_ANCHORS)
    anchors = list(range(first_anchor, last_valid_anchor))
    print(f"Anchors: {len(anchors)}  (range index {anchors[0]} → {anchors[-1]})")

    # Per-pair MAE accumulators (3 baselines: TimeXer, plain ARIMA, SARIMAX)
    timexer_errors = {c: [] for c in col_names}
    arima_errors = {c: [] for c in col_names}
    sarimax_errors = {c: [] for c in col_names}

    for ai, a in enumerate(anchors):
        history = X[:a]
        truth = X[a: a + PRED_LEN]   # (PRED_LEN, NUM_VARS)

        # ---- TimeXer forecast ----
        last = history[-SEQ_LEN:]
        last_n = (last - mean) / std
        x_t = torch.from_numpy(last_n).unsqueeze(0).to(device)
        x_mark = torch.zeros(1, SEQ_LEN, 4, device=device)
        y_mark = torch.zeros(1, PRED_LEN, 4, device=device)
        dec_inp = torch.zeros(1, PRED_LEN, NUM_VARS, device=device)
        with torch.no_grad():
            out = model(x_t, x_mark, dec_inp, y_mark)
        timexer_pred = out.squeeze(0).cpu().numpy() * std + mean   # (PRED_LEN, NUM_VARS)

        # ---- ARIMA(1,1,1) baseline (per column) ----
        arima_pred = np.zeros_like(truth)
        sarimax_pred = np.zeros_like(truth)
        for j in range(NUM_VARS):
            arima_pred[:, j] = arima_forecast(history[:, j], PRED_LEN, seasonal=False)
            sarimax_pred[:, j] = sarimax_forecast(history[:, j], PRED_LEN)

        # Accumulate per-pair MAE for this anchor
        for j, c in enumerate(col_names):
            timexer_errors[c].append(np.mean(np.abs(timexer_pred[:, j] - truth[:, j])))
            arima_errors[c].append(np.mean(np.abs(arima_pred[:, j] - truth[:, j])))
            sarimax_errors[c].append(np.mean(np.abs(sarimax_pred[:, j] - truth[:, j])))

        if (ai + 1) % 5 == 0:
            print(f"  [{ai+1:3d}/{len(anchors)}] anchor done")

    # Aggregate
    print("\n" + "=" * 92)
    print(f"{'Pair':<10} {'TimeXer':>10} {'ARIMA':>10} {'SARIMAX':>10}"
          f"  {'TX vs ARIMA':>14}  {'TX vs SARIMAX':>14}")
    print("=" * 92)

    overall_tx, overall_ar, overall_sx = [], [], []
    per_pair = {}
    for c in col_names:
        tx = float(np.mean(timexer_errors[c]))
        ar = float(np.mean(arima_errors[c]))
        sx = float(np.mean(sarimax_errors[c]))
        imp_ar = (ar - tx) / ar * 100 if ar > 0 else 0
        imp_sx = (sx - tx) / sx * 100 if sx > 0 else 0
        per_pair[c] = {"timexer_mae": tx, "arima_mae": ar, "sarimax_mae": sx,
                       "vs_arima_pct": imp_ar, "vs_sarimax_pct": imp_sx}
        overall_tx.extend(timexer_errors[c])
        overall_ar.extend(arima_errors[c])
        overall_sx.extend(sarimax_errors[c])
        print(f"{c:<10} {tx:>10.4f} {ar:>10.4f} {sx:>10.4f}  {imp_ar:>13.2f}%  {imp_sx:>13.2f}%")

    overall_tx_mae = float(np.mean(overall_tx))
    overall_ar_mae = float(np.mean(overall_ar))
    overall_sx_mae = float(np.mean(overall_sx))
    overall_imp_ar = (overall_ar_mae - overall_tx_mae) / overall_ar_mae * 100
    overall_imp_sx = (overall_sx_mae - overall_tx_mae) / overall_sx_mae * 100
    print("=" * 92)
    print(f"{'OVERALL':<10} {overall_tx_mae:>10.4f} {overall_ar_mae:>10.4f} {overall_sx_mae:>10.4f}"
          f"  {overall_imp_ar:>13.2f}%  {overall_imp_sx:>13.2f}%")
    print("=" * 92)

    out_path = Path("D:/temp_resume/backtest.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps({
        "n_anchors": len(anchors),
        "seq_len": SEQ_LEN, "pred_len": PRED_LEN,
        "per_pair": per_pair,
        "overall": {
            "timexer_mae": overall_tx_mae,
            "arima_mae": overall_ar_mae,
            "sarimax_mae": overall_sx_mae,
            "vs_arima_pct": overall_imp_ar,
            "vs_sarimax_pct": overall_imp_sx,
        },
    }, indent=2), encoding="utf-8")
    print(f"\nResults saved: {out_path}")


if __name__ == "__main__":
    main()
