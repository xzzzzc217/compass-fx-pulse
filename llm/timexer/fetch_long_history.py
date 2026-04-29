"""Pull 25-year ECB exchange-rate history for TimeXer scaling experiment.

Production DB (historicaldata) only has 2024-01-01 onwards. For TimeXer
training, we want as much history as ECB has: 1999-01-04 (EUR launch) → today.

Saves CSV to llm/timexer/data/fx_long.csv (not into MySQL — keeps production
DB clean).
"""
from __future__ import annotations

import sys
import time
from datetime import date
from pathlib import Path

import pandas as pd
import requests

CURRENCIES = ["USD", "GBP", "EUR", "JPY", "HKD", "AUD"]
START = "1999-01-04"  # EUR introduction = earliest ECB reference rate
END = date.today().isoformat()

OUT_DIR = Path(__file__).resolve().parent / "data"
OUT_CSV = OUT_DIR / "fx_long.csv"


def fetch(base: str, quotes: list[str], start: str, end: str,
          retries: int = 3) -> dict[str, dict[str, float]]:
    url = f"https://api.frankfurter.app/{start}..{end}"
    params = {"from": base, "to": ",".join(quotes)}
    for attempt in range(1, retries + 1):
        try:
            r = requests.get(url, params=params, timeout=60)
            r.raise_for_status()
            return r.json().get("rates", {})
        except Exception as exc:
            print(f"    attempt {attempt}: {exc}")
            time.sleep(2 * attempt)
    return {}


def main() -> None:
    print(f"Fetching ECB rates {START} → {END} via frankfurter.app")
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # Pull base=USD rates against the other 5 currencies
    quotes = [c for c in CURRENCIES if c != "USD"]
    print(f"  base=USD, quotes={quotes}")
    rates_by_date = fetch("USD", quotes, START, END)
    print(f"  got {len(rates_by_date)} dates")
    if not rates_by_date:
        print("FAIL: no data returned")
        sys.exit(1)

    # Normalize to DataFrame: date × {EUR,GBP,JPY,HKD,AUD}
    rows = []
    for d, day_rates in sorted(rates_by_date.items()):
        row = {"date": d}
        for q in quotes:
            row[f"USD_{q}"] = day_rates.get(q)
        rows.append(row)
    df = pd.DataFrame(rows).set_index("date")
    df.index = pd.to_datetime(df.index)
    df = df.asfreq("B").interpolate(method="time")

    # Drop early period where some currencies have no data (e.g. HKD/AUD pre-2002)
    n_before = len(df)
    df = df.dropna()
    print(f"  rows: {n_before} → {len(df)} after dropping rows with NaN")
    print(f"  effective range: {df.index.min().date()} → {df.index.max().date()}")
    print(f"  columns: {list(df.columns)}")

    df.to_csv(OUT_CSV)
    print(f"Saved {OUT_CSV} ({OUT_CSV.stat().st_size / 1024:.1f} KB)")
    print()
    print("Sample (first 3, last 3):")
    print(df.head(3))
    print(df.tail(3))


if __name__ == "__main__":
    main()
