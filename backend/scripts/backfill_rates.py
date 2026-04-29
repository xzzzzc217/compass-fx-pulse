"""Backfill historicaldata table from frankfurter.app (ECB reference rates).

Usage:
    python scripts/backfill_rates.py                      # 2024-01-01 → today
    python scripts/backfill_rates.py 2025-01-01           # custom start
    python scripts/backfill_rates.py 2025-01-01 2026-04-28

Why frankfurter.app:
    - Free, no API key, no aggressive rate limit (vs yfinance 429s)
    - ECB official reference rates → trustworthy enough to talk about in interviews
    - Covers all 6 currencies we need (USD/GBP/EUR/JPY/HKD/AUD)
    - One API call returns the full date range for one base vs many quotes

Strategy:
    - 6 API calls total (one per base currency, asking for all 5 quotes at once)
    - 30 directed pairs covered. Idempotent upsert into MySQL.
"""
from __future__ import annotations

import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path

import requests

# allow `from app.db import ...` when run from repo root
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.db import get_cursor  # noqa: E402

CURRENCIES = ["USD", "GBP", "EUR", "JPY", "HKD", "AUD"]
API = "https://api.frankfurter.app/{start}..{end}"
DAILY_TIME = "18:00:00"  # match original schema (ECB publishes ~16:00 CET)


def _fetch(base: str, quotes: list[str], start: str, end: str,
           retries: int = 3) -> dict[str, dict[str, float]]:
    url = API.format(start=start, end=end)
    params = {"from": base, "to": ",".join(quotes)}
    for attempt in range(1, retries + 1):
        try:
            r = requests.get(url, params=params, timeout=30)
            r.raise_for_status()
            data = r.json()
            return data.get("rates", {})
        except Exception as exc:
            print(f"    attempt {attempt}/{retries} failed: {exc}")
            if attempt < retries:
                time.sleep(2 * attempt)
    return {}


def _upsert(rows: list[tuple[str, str, str, float]]) -> int:
    if not rows:
        return 0
    sql = """
        INSERT INTO historicaldata (currencytype1, currencytype2, time, rate)
        VALUES (%s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE rate = VALUES(rate)
    """
    with get_cursor(commit=True) as cur:
        cur.executemany(sql, rows)
        return cur.rowcount


def backfill(start: str, end: str) -> None:
    print(f"Backfilling {start} → {end} via frankfurter.app (ECB)")
    print(f"Currencies: {CURRENCIES}  ({len(CURRENCIES) * (len(CURRENCIES) - 1)} directed pairs)")
    print()

    all_rows: list[tuple[str, str, str, float]] = []
    for base in CURRENCIES:
        quotes = [c for c in CURRENCIES if c != base]
        print(f"  fetching base={base} → {quotes} ...", end=" ", flush=True)
        rates_by_date = _fetch(base, quotes, start, end)
        if not rates_by_date:
            print("EMPTY")
            continue

        n = 0
        for d, day_rates in rates_by_date.items():
            ts = f"{d} {DAILY_TIME}"
            for quote, rate in day_rates.items():
                all_rows.append((base, quote, ts, float(rate)))
                n += 1
        print(f"{n} rows ({len(rates_by_date)} days)")

    affected = _upsert(all_rows)
    print()
    print(f"Done. {len(all_rows)} rows submitted, {affected} affected (insert+update).")

    if all_rows:
        # Quick sanity peek for the user
        with get_cursor() as cur:
            cur.execute(
                "SELECT MIN(time), MAX(time), COUNT(*) FROM historicaldata"
            )
            mn, mx, cnt = cur.fetchone()
            print(f"DB now: {cnt} rows, {mn} → {mx}")


def _parse_date(s: str) -> str:
    datetime.strptime(s, "%Y-%m-%d")
    return s


if __name__ == "__main__":
    args = sys.argv[1:]
    start = args[0] if len(args) >= 1 else "2024-01-01"
    end = args[1] if len(args) >= 2 else date.today().isoformat()
    backfill(_parse_date(start), _parse_date(end))
