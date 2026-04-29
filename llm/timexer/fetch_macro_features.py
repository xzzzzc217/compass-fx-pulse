"""Fetch macro/exogenous features for TimeXer-MS experiment.

The original 花旗杯 project's TimeXer setup was forecast_exogenous (features=MS,
enc_in=3, c_out=1) — the 3 inputs were meant to be (rate, exog_1, exog_2). The
team designed news-scoring as exog but never produced a 25-year history.

We instead use the textbook FX macro drivers, all freely available from FRED:
  - DFF: Federal funds effective rate (daily)
  - VIXCLS: CBOE Volatility Index (daily, "fear gauge")
  - DTWEXBGS: Trade-weighted USD index (daily, USD broad strength)
  + Foreign policy rates (one per non-USD currency):
  - ECBDFR / IRLTLT01EZM156N: Eurozone
  - IUDSOIA / IR3TIB01GBM156N: UK (BoE Bank Rate)
  - IR3TIB01JPM156N / IRLTLT01JPM156N: Japan
  - IR3TIB01AUM156N: Australia
  (HKD is pegged to USD → "rate diff" ≈ 0, expect TimeXer = ARIMA on HKD)

For each currency pair USD/X, the feature matrix is:
    [rate, US_rate - foreign_rate, VIXCLS]
matching the original `enc_in=3` setup.

Saved to llm/timexer/data/fx_macro.csv.
"""
from __future__ import annotations

import io
import sys
import time
from pathlib import Path

import pandas as pd
import requests

OUT = Path(__file__).resolve().parent / "data" / "fx_macro.csv"

# FRED CSV download endpoint (no API key needed, public)
FRED_CSV = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={series}"

SERIES = {
    "DFF": "us_rate",          # US fed funds effective (daily)
    "VIXCLS": "vix",           # CBOE VIX (daily)
    "DTWEXBGS": "dxy",         # Trade-weighted USD broad
    # Eurozone main refinancing rate proxy (ECB deposit facility rate, daily)
    "ECBDFR": "eu_rate",
    # UK Bank rate (daily proxy)
    "IUDSOIA": "uk_rate",
    # Japan: short-term interbank rate (monthly only on FRED → forward-fill daily)
    "IRSTCI01JPM156N": "jp_rate",
    # Australia: 3-month interbank (monthly, fwd-fill)
    "IR3TIB01AUM156N": "au_rate",
}


def fetch_one(series: str, name: str) -> pd.Series | None:
    url = FRED_CSV.format(series=series)
    print(f"  fetching {series} ({name}) ...", end=" ", flush=True)
    # Try through user's HTTP proxy (Clash) since direct connect to fred.stlouisfed.org
    # fails on Chinese networks. SSL verification disabled for proxy MITM.
    import os
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    proxies = {
        "http": os.environ.get("HTTP_PROXY") or os.environ.get("http_proxy"),
        "https": os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy"),
    }
    proxies = {k: v for k, v in proxies.items() if v}

    for attempt in range(3):
        try:
            r = requests.get(url, timeout=60, proxies=proxies, verify=False)
            r.raise_for_status()
            df = pd.read_csv(io.BytesIO(r.content))
            # Newer FRED CSV uses 'observation_date', older 'DATE'
            date_col = "observation_date" if "observation_date" in df.columns else "DATE"
            value_col = [c for c in df.columns if c not in (date_col,)][0]
            df = df.rename(columns={date_col: "date", value_col: name})
            df["date"] = pd.to_datetime(df["date"])
            df = df.set_index("date")
            df[name] = pd.to_numeric(df[name], errors="coerce")
            df = df.dropna()
            print(f"{len(df)} rows")
            return df[name]
        except Exception as exc:
            print(f"  attempt {attempt+1}: {exc}")
            time.sleep(2)
    print("FAIL")
    return None


def main() -> None:
    print("Fetching macro series from FRED ...")
    series = {}
    for fred_id, name in SERIES.items():
        s = fetch_one(fred_id, name)
        if s is not None:
            series[name] = s

    if not series:
        sys.exit(1)

    df = pd.concat(series, axis=1).asfreq("B")
    # Forward-fill monthly series (jp/au), interpolate VIX/USD short gaps
    df = df.ffill().interpolate(method="time", limit=10)
    df = df.dropna(how="all")

    print(f"\nMerged: {df.shape}, range {df.index.min().date()} → {df.index.max().date()}")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUT)
    print(f"Saved {OUT}")
    print()
    print("Tail:")
    print(df.tail(3))
    print()
    print("Coverage (first non-NaN per column):")
    for col in df.columns:
        first = df[col].first_valid_index()
        print(f"  {col}: {first.date() if first else 'NEVER'}")


if __name__ == "__main__":
    main()
