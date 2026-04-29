"""Build the per-pair 11-feature matrix matching the original 花旗杯 design.

Features (target last, per TimeXer-MS convention):
    [us_cpi, country_cpi, us_inflation, wti, us10y, us_m2, dow, day, month, dxy, rate]

= 10 exogenous + 1 target = 11, matching the architecture doc:
    CPI_tok, 利率_tok, 油价_tok, GDP_tok, 通胀_tok, M2_tok, dow_tok, day_tok, month_tok, hour_tok→dxy_substitute, rate

(hour_tok skipped — daily FX has no intraday; substituted with DXY for global USD strength.)

Country-specific (for the foreign currency in the pair):
    USD_EUR → uses some EU/UK macro (fallback US since WB EU coverage spotty)
    USD_GBP → uses UK macro
    USD_JPY → uses JP macro
    USD_HKD → uses HK macro
    USD_AUD → uses AU macro

Output: per-pair DataFrame indexed by date, 11 columns, target='rate' last.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

DATA_DIR = Path(__file__).resolve().parent / "data"
FX_LONG = DATA_DIR / "fx_long.csv"
WB_CSV = DATA_DIR / "fx_macro_wb.csv"
MARKET_CSV = DATA_DIR / "fx_market.csv"

# Pair → country code in WB CSV
PAIR_COUNTRY = {
    "USD_EUR": "uk",   # EU coverage spotty in WB; UK is closest proxy for European bloc
    "USD_GBP": "uk",
    "USD_JPY": "jp",
    "USD_HKD": "hk",
    "USD_AUD": "au",
}


def _load_inputs() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    fx = pd.read_csv(FX_LONG, parse_dates=["date"]).set_index("date")
    wb = pd.read_csv(WB_CSV, index_col=0, parse_dates=True)
    mkt = pd.read_csv(MARKET_CSV, index_col=0, parse_dates=True)
    return fx, wb, mkt


def build(pair: str, mode: str = "v2") -> pd.DataFrame:
    """Return DataFrame with target 'rate' as the LAST column.

    mode='v1': 11 raw features (us_cpi, country_cpi, us_inflation, wti, us10y,
               us_m2, dow, day, month, dxy, rate) — matches resume's listed
               architecture but yearly macro = noise at daily resolution.
    mode='v2': 9 daily-moving features with cyclic time encoding (recommended).
               (us10y, wti, vix, dxy, sin_dow, cos_dow, sin_month, cos_month, rate)
    """
    if pair not in PAIR_COUNTRY:
        raise ValueError(f"unknown pair {pair}")
    country = PAIR_COUNTRY[pair]
    fx, wb, mkt = _load_inputs()
    out = pd.DataFrame(index=fx.index)

    if mode == "v1":
        out["us_cpi"] = wb["us_cpi"].reindex(out.index, method="ffill")
        if f"{country}_cpi" in wb.columns:
            out["country_cpi"] = wb[f"{country}_cpi"].reindex(out.index, method="ffill")
        else:
            out["country_cpi"] = out["us_cpi"]
        out["us_inflation"] = wb["us_inflation"].reindex(out.index, method="ffill")
        out["wti"] = mkt["wti"].reindex(out.index, method="ffill")
        out["us10y"] = mkt["us10y"].reindex(out.index, method="ffill")
        out["us_m2"] = wb["us_m2"].reindex(out.index, method="ffill")
        out["dow"] = out.index.dayofweek.astype(np.float32)
        out["day"] = out.index.day.astype(np.float32)
        out["month"] = out.index.month.astype(np.float32)
        out["dxy"] = mkt["dxy"].reindex(out.index, method="ffill")

    elif mode == "v2":
        # Daily-moving market drivers
        out["us10y"] = mkt["us10y"].reindex(out.index, method="ffill")
        out["wti"] = mkt["wti"].reindex(out.index, method="ffill")
        out["vix"] = mkt["vix"].reindex(out.index, method="ffill")
        out["dxy"] = mkt["dxy"].reindex(out.index, method="ffill")
        # Cyclical time encoding (preserves continuity between Sunday-Monday and Dec-Jan)
        dow = out.index.dayofweek.values
        month = out.index.month.values
        out["sin_dow"] = np.sin(2 * np.pi * dow / 7).astype(np.float32)
        out["cos_dow"] = np.cos(2 * np.pi * dow / 7).astype(np.float32)
        out["sin_month"] = np.sin(2 * np.pi * (month - 1) / 12).astype(np.float32)
        out["cos_month"] = np.cos(2 * np.pi * (month - 1) / 12).astype(np.float32)

    elif mode == "v3":
        # Hybrid: vol+mom (rate-derived, technical) + VIX + DXY (cross-market)
        rates = fx[pair]
        log_ret = np.log(rates).diff()
        out["vol_20d"] = log_ret.rolling(20).std()
        out["mom_5d"] = rates.pct_change(5)
        out["vix"] = mkt["vix"].reindex(out.index, method="ffill")
        out["dxy"] = mkt["dxy"].reindex(out.index, method="ffill")

    else:
        raise ValueError(f"unknown mode {mode}")

    # TARGET (always last column, per TimeXer MS convention)
    out["rate"] = fx[pair]

    return out.dropna().astype(np.float32)


if __name__ == "__main__":
    import sys
    p = sys.argv[1] if len(sys.argv) > 1 else "USD_EUR"
    df = build(p)
    print(f"Pair: {p}")
    print(f"Shape: {df.shape}")
    print(f"Range: {df.index.min().date()} → {df.index.max().date()}")
    print(f"Columns: {list(df.columns)}")
    print()
    print("Head:")
    print(df.head(3))
    print()
    print("Tail:")
    print(df.tail(3))
