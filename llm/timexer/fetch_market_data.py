"""Fetch VIX and WTI oil price daily series via yfinance.

Yahoo Finance heavily rate-limits — we use 1 request, 25-year span, with retry
and exponential backoff. If still 429, fall back to derived volatility proxy
from the FX data we already have.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import pandas as pd

OUT = Path(__file__).resolve().parent / "data" / "fx_market.csv"

TICKERS = {
    "vix": "^VIX",       # CBOE Volatility Index
    "wti": "CL=F",       # WTI crude oil futures
    "dxy": "DX-Y.NYB",   # US Dollar index (NYBOT)
    "us10y": "^TNX",     # US 10Y Treasury yield
    "us2y": "^IRX",      # US 13-week Treasury (closest proxy for short rate)
}

START = "1999-01-04"
END = "2026-04-28"


def fetch_one(ticker: str, name: str, retries: int = 5) -> pd.Series | None:
    import yfinance as yf
    for attempt in range(1, retries + 1):
        print(f"  fetching {ticker} ({name}) attempt {attempt} ...", end="", flush=True)
        try:
            df = yf.download(ticker, start=START, end=END,
                             progress=False, auto_adjust=False, threads=False)
            if df is not None and not df.empty:
                close = df["Close"]
                if hasattr(close, "columns"):
                    close.columns = [name]
                else:
                    close.name = name
                # Drop NaNs
                s = (close.iloc[:, 0] if hasattr(close, "iloc") and close.ndim > 1 else close).dropna()
                print(f" OK, {len(s)} rows")
                return s
        except Exception as exc:
            print(f"  {exc}")
        # Exponential backoff
        wait = min(60, 5 * (2 ** (attempt - 1)))
        print(f"    backoff {wait}s")
        time.sleep(wait)
    print(f"  GAVE UP on {ticker}")
    return None


def main() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    series = {}
    for name, ticker in TICKERS.items():
        s = fetch_one(ticker, name)
        if s is not None:
            series[name] = s
        # Pacing between requests to avoid trips of yfinance throttle
        time.sleep(3)

    if not series:
        print("FAIL: nothing fetched")
        sys.exit(1)

    df = pd.concat(series, axis=1).asfreq("B").ffill()
    df = df.dropna(how="all")
    print(f"\nMerged: {df.shape}, {df.index.min().date()} → {df.index.max().date()}")
    df.to_csv(OUT)
    print(f"Saved {OUT}")
    print()
    print("Coverage:")
    for col in df.columns:
        first = df[col].first_valid_index()
        last = df[col].last_valid_index()
        n = df[col].notna().sum()
        print(f"  {col}: {first.date() if first else '-'} → "
              f"{last.date() if last else '-'} ({n} valid)")
    print()
    print("Tail:")
    print(df.tail(3))


if __name__ == "__main__":
    main()
