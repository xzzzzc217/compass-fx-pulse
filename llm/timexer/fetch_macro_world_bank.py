"""Fetch macro indicators from World Bank Open Data API (no auth, no rate limit).

For each country: CPI, GDP (real), M2 money supply, inflation (CPI YoY %).
Country mapping (USD-X target → country whose macro to fetch):
  USD/EUR → EU aggregate
  USD/GBP → United Kingdom
  USD/JPY → Japan
  USD/HKD → Hong Kong SAR
  USD/AUD → Australia
Plus US baseline.

WB indicator codes:
  - FP.CPI.TOTL: CPI (2010=100, annual)
  - FP.CPI.TOTL.ZG: Inflation (CPI YoY %, annual)
  - NY.GDP.MKTP.CD: GDP (current US$, annual)
  - FM.LBL.BMNY.CN: Broad money M2 (LCU, annual)

Caveat: World Bank only publishes ANNUAL data. We forward-fill to daily.
Better than nothing — captures regime changes (e.g. 2008 crisis, 2020 COVID).

Output: llm/timexer/data/fx_macro_wb.csv (date × {us_cpi, us_gdp, ... country_*})
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import pandas as pd
import requests

OUT = Path(__file__).resolve().parent / "data" / "fx_macro_wb.csv"

WB_BASE = "https://api.worldbank.org/v2/country/{code}/indicator/{ind}?format=json&date=1999:2026&per_page=300"

COUNTRIES = {
    "us": "US",       # United States
    "eu": "EUU",      # European Union
    "uk": "GB",       # United Kingdom
    "jp": "JP",       # Japan
    "hk": "HK",       # Hong Kong
    "au": "AU",       # Australia
}

INDICATORS = {
    "cpi":       "FP.CPI.TOTL",        # CPI index (2010=100)
    "inflation": "FP.CPI.TOTL.ZG",     # Inflation YoY %
    "gdp":       "NY.GDP.MKTP.CD",     # GDP current US$
    "m2":        "FM.LBL.BMNY.CN",     # Broad money (LCU)
}


def fetch_indicator(country: str, ind: str) -> pd.Series | None:
    url = WB_BASE.format(code=country, ind=ind)
    proxies = {
        "http": os.environ.get("HTTP_PROXY") or os.environ.get("http_proxy"),
        "https": os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy"),
    }
    proxies = {k: v for k, v in proxies.items() if v}
    for attempt in range(3):
        try:
            r = requests.get(url, timeout=30, proxies=proxies, verify=False)
            r.raise_for_status()
            data = r.json()
            if not isinstance(data, list) or len(data) < 2 or not data[1]:
                print(f"    no data for {country}/{ind}")
                return None
            rows = [(int(d["date"]), d["value"]) for d in data[1]
                    if d.get("value") is not None]
            if not rows:
                return None
            df = pd.DataFrame(rows, columns=["year", "value"]).sort_values("year")
            return df.set_index("year")["value"]
        except Exception as exc:
            print(f"    {country}/{ind} attempt {attempt+1}: {exc}")
            time.sleep(1)
    return None


def yearly_to_daily(series: pd.Series, start: str = "1999-01-04",
                    end: str = "2026-04-27") -> pd.Series:
    """Forward-fill annual values to daily business-day index."""
    # Year x → assigned to Jan 1 of x, ffilled through year-end
    s = series.copy()
    s.index = pd.to_datetime([f"{y}-01-01" for y in s.index])
    daily_idx = pd.date_range(start, end, freq="B")
    s = s.reindex(daily_idx, method="ffill")
    return s.astype(float)


def main() -> None:
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    print("Fetching World Bank macro indicators ...")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    cols: dict[str, pd.Series] = {}

    for c_short, c_code in COUNTRIES.items():
        for ind_short, ind_code in INDICATORS.items():
            print(f"  {c_short}/{ind_short} ({c_code}/{ind_code}) ...", end="", flush=True)
            s = fetch_indicator(c_code, ind_code)
            if s is None or len(s) == 0:
                print(" (skipped)")
                continue
            print(f" {s.index.min()}→{s.index.max()}, {len(s)} years")
            cols[f"{c_short}_{ind_short}"] = yearly_to_daily(s)

    if not cols:
        print("FAIL: no data fetched")
        sys.exit(1)

    df = pd.DataFrame(cols)
    print(f"\nMerged: {df.shape}, {df.index.min().date()} → {df.index.max().date()}")
    df.to_csv(OUT)
    print(f"Saved {OUT} ({OUT.stat().st_size/1024:.1f} KB)")
    print()
    print("Tail (last 3 rows):")
    print(df.tail(3))


if __name__ == "__main__":
    main()
