"""One-shot data refresh: pull latest rates + regenerate forecasts.

Run this daily (or whenever you want fresh data + predictions).

Usage:
    python scripts/refresh.py                       # default: today's rates + 30d forecast
    python scripts/refresh.py --no-predictions      # just refresh rates
    python scripts/refresh.py --horizon 60          # 60-day forecast
"""
from __future__ import annotations

import argparse
import os
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
os.environ.setdefault("OMP_NUM_THREADS", "1")

import subprocess
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent  # backend/


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--start", default="2024-01-01")
    p.add_argument("--end", default=None, help="default: today")
    p.add_argument("--horizon", type=int, default=30)
    p.add_argument("--no-predictions", action="store_true")
    args = p.parse_args()

    end = args.end or date.today().isoformat()

    py = sys.executable

    print("=" * 60)
    print(f"[1/2] Refreshing historical rates ({args.start} → {end}) ...")
    print("=" * 60)
    r = subprocess.run(
        [py, str(ROOT / "scripts" / "backfill_rates.py"), args.start, end],
        cwd=str(ROOT),
    )
    if r.returncode != 0:
        sys.exit(r.returncode)

    if args.no_predictions:
        print("Skipping predictions (--no-predictions).")
        return

    print()
    print("=" * 60)
    print(f"[2/2] Regenerating {args.horizon}-day forecasts ...")
    print("=" * 60)
    r = subprocess.run(
        [py, str(ROOT / "scripts" / "predict_rates.py"),
         "--horizon", str(args.horizon)],
        cwd=str(ROOT),
    )
    sys.exit(r.returncode)


if __name__ == "__main__":
    main()
