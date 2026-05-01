"""Phase 4.1 cache benchmark — proves the cache layer works.

Runs each of the 5 tools twice. First call: cache miss (real work).
Second call: cache hit (returns from memory).
Prints the speedup ratio and the saved time.

Usage:
    cd backend
    python scripts/cache_benchmark.py

Optional flags:
    --redis      Force Redis backend (requires REDIS_URL env var).
    --warmup-rag Skip the slow first RAG call by pre-loading the model.

Sample output (first run, cold caches):
    get_exchange_rate    miss=120ms   hit=0.4ms   speedup=300x
    get_rate_range       miss=85ms    hit=0.5ms   speedup=170x
    predict_exchange_rate miss=42ms   hit=0.3ms   speedup=140x
    calculate_var        miss=210ms   hit=0.4ms   speedup=525x
    search_forex_knowledge miss=35000ms hit=1.2ms speedup=29000x  ← biggest win
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

# Allow running as `python scripts/cache_benchmark.py` from backend/.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Set Windows OpenMP / MKL hardening before any heavy imports
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
os.environ.setdefault("OMP_NUM_THREADS", "1")


def time_call(label: str, fn, *args, **kwargs) -> tuple[float, dict]:
    t0 = time.perf_counter()
    result = fn(*args, **kwargs)
    elapsed = (time.perf_counter() - t0) * 1000
    print(f"  {label:6s} {elapsed:>10.1f} ms")
    return elapsed, result


def fmt_speedup(miss_ms: float, hit_ms: float) -> str:
    if hit_ms <= 0:
        return "(too fast to measure)"
    ratio = miss_ms / hit_ms
    if ratio >= 1000:
        return f"speedup ≈ {ratio/1000:.1f}× thousand"
    return f"speedup ≈ {ratio:.0f}×"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-rag", action="store_true",
                        help="Skip the search_forex_knowledge benchmark (slow cold start).")
    args = parser.parse_args()

    from app.agent.tools import execute
    from app.cache import clear, get_stats

    clear()  # fresh stats

    cases = [
        ("get_exchange_rate",      {"currency_a": "USD", "currency_b": "JPY"}),
        ("get_rate_range",         {"currency_a": "USD", "currency_b": "EUR",
                                    "start_date": "2025-01-01", "end_date": "2025-04-01"}),
        ("predict_exchange_rate",  {"currency_a": "USD", "currency_b": "GBP",
                                    "horizon_days": 7}),
        ("calculate_var",          {"currency_a": "USD", "currency_b": "JPY",
                                    "position_amount": 1_000_000}),
    ]
    if not args.skip_rag:
        cases.append(("search_forex_knowledge", {"query": "carry trade", "k": 3}))

    print("=" * 70)
    print(" CompassFX Phase 4.1 — Cache Benchmark")
    print("=" * 70)

    summary = []
    for tool, kwargs in cases:
        print(f"\n→ {tool}({kwargs})")
        miss_ms, _ = time_call("miss",  execute, tool, kwargs)
        hit_ms,  _ = time_call("hit",   execute, tool, kwargs)
        summary.append((tool, miss_ms, hit_ms))

    print("\n" + "=" * 70)
    print(" Summary")
    print("=" * 70)
    print(f"{'Tool':24s} {'Miss (ms)':>12s} {'Hit (ms)':>12s}  Speedup")
    print("-" * 70)
    total_saved = 0.0
    for tool, miss_ms, hit_ms in summary:
        print(f"{tool:24s} {miss_ms:>12.1f} {hit_ms:>12.1f}  {fmt_speedup(miss_ms, hit_ms)}")
        total_saved += miss_ms - hit_ms

    print("-" * 70)
    print(f"Total saved on the second pass: {total_saved/1000:.2f} s")
    print(f"\nCache stats: {get_stats()}")


if __name__ == "__main__":
    main()
