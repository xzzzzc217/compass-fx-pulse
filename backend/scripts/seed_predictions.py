"""Seed predictdata with a placeholder forecast so the prediction page renders.

Phase 0 only. Uses a 30-day rolling-mean extension as the 'forecast'.
Phase 2 will replace this with TimeXer model predictions.
"""
from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.db import get_cursor  # noqa: E402

HORIZON_DAYS = 30


def seed() -> None:
    pairs: list[tuple[str, str]] = []
    with get_cursor() as cur:
        cur.execute(
            "SELECT DISTINCT currencytype1, currencytype2 FROM historicaldata"
        )
        pairs = [(r[0], r[1]) for r in cur.fetchall()]

    if not pairs:
        print("historicaldata is empty. Run backfill_rates.py first.")
        return

    rows: list[tuple[str, str, str, float]] = []
    today = date.today()
    for a, b in pairs:
        with get_cursor() as cur:
            cur.execute(
                """
                SELECT AVG(rate) FROM (
                    SELECT rate FROM historicaldata
                    WHERE currencytype1 = %s AND currencytype2 = %s
                    ORDER BY time DESC LIMIT 30
                ) t
                """,
                (a, b),
            )
            avg = cur.fetchone()[0]
        if avg is None:
            continue
        for d in range(1, HORIZON_DAYS + 1):
            ts = (today + timedelta(days=d)).strftime("%Y-%m-%d %H:%M:%S")
            rows.append((a, b, ts, float(avg)))

    sql = """
        INSERT INTO predictdata (currencytype1, currencytype2, time, rate)
        VALUES (%s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE rate = VALUES(rate)
    """
    with get_cursor(commit=True) as cur:
        cur.executemany(sql, rows)
        print(f"Seeded {len(rows)} placeholder predictions across {len(pairs)} pairs.")


if __name__ == "__main__":
    seed()
