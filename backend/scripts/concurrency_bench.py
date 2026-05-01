"""Phase 4.4 — concurrency benchmark: Flask sync vs FastAPI async.

Hits a target server with N concurrent /api/agent requests, measures:
  - total wall time
  - per-request latency (mean / p50 / p95)
  - effective QPS

Quick start (two terminals):

    # Terminal 1: Flask
    python main.py
    # Terminal 2: FastAPI
    uvicorn main_fastapi:app --host 0.0.0.0 --port 8082 --workers 1
    # Terminal 3 (this script): bench both
    python scripts/concurrency_bench.py --concurrency 5

Single-server bench:
    python scripts/concurrency_bench.py --target flask --concurrency 5
    python scripts/concurrency_bench.py --target fastapi --concurrency 5
"""
from __future__ import annotations

import argparse
import asyncio
import statistics
import time
from urllib.parse import quote

import httpx

DEFAULT_QUERIES = [
    "美元兑日元最新汇率多少？",
    "美元兑欧元最新汇率",
    "USD/GBP 当前汇率",
    "美元兑日元在 2026 年 4 月的统计",
    "什么是 carry trade",
    "VaR 是什么",
    "100 万美元美元日元 1 天 99% VaR",
    "预测未来 7 天 USD/GBP",
]


async def hit_one(client: httpx.AsyncClient, base: str, query: str,
                  endpoint: str = "agent") -> tuple[float, bool]:
    """Send one request, drain response, return (elapsed_sec, ok).

    Endpoint options:
      - agent: streaming /api/agent with the query (slow, ~5-15s)
      - rates: /api/rates/recent (quick SQL, ~50ms — best for pure
               framework concurrency demo)
      - health: /api/health (cheapest)
    """
    if endpoint == "rates":
        url = f"{base}/api/rates/recent?currency_a=USD&currency_b=JPY&limit=30"
    elif endpoint == "health":
        url = f"{base}/api/health"
    else:
        url = f"{base}/api/agent?query={quote(query)}&trace=0"

    t0 = time.perf_counter()
    try:
        if endpoint == "agent":
            async with client.stream("GET", url, timeout=180.0) as resp:
                if resp.status_code != 200:
                    return time.perf_counter() - t0, False
                async for _chunk in resp.aiter_bytes():
                    pass
        else:
            resp = await client.get(url, timeout=30.0)
            if resp.status_code != 200:
                return time.perf_counter() - t0, False
        return time.perf_counter() - t0, True
    except Exception as e:
        print(f"   (err: {e})", flush=True)
        return time.perf_counter() - t0, False


async def run_bench(base: str, concurrency: int, queries: list[str],
                    endpoint: str = "agent") -> dict:
    """Fire N concurrent requests and collect timing."""
    async with httpx.AsyncClient(http2=False) as client:
        # warm up: one sequential call to amortize first-RAG / connection setup
        print(f"   [warmup] {base} {endpoint}", flush=True)
        await hit_one(client, base, queries[0], endpoint)

        print(f"   [bench]  {concurrency} concurrent /api/{endpoint} calls...", flush=True)
        t0 = time.perf_counter()
        tasks = [hit_one(client, base, queries[i % len(queries)], endpoint)
                 for i in range(concurrency)]
        results = await asyncio.gather(*tasks)
        wall = time.perf_counter() - t0

    latencies_ok = [t for t, ok in results if ok]
    n_ok = len(latencies_ok)
    n_fail = len(results) - n_ok
    if not latencies_ok:
        return {"base": base, "concurrency": concurrency, "wall_sec": round(wall, 2),
                "n_ok": 0, "n_fail": n_fail, "mean_sec": 0, "median_sec": 0,
                "p95_sec": 0, "qps": 0.0, "issue": "all failed"}

    mean = statistics.mean(latencies_ok)
    median = statistics.median(latencies_ok)
    p95 = statistics.quantiles(latencies_ok, n=20)[18] if len(latencies_ok) > 1 else mean

    return {
        "base": base,
        "concurrency": concurrency,
        "wall_sec": round(wall, 2),
        "n_ok": n_ok,
        "n_fail": n_fail,
        "mean_sec": round(mean, 2),
        "median_sec": round(median, 2),
        "p95_sec": round(p95, 2),
        "qps": round(n_ok / wall, 2),
    }


async def main():
    p = argparse.ArgumentParser()
    p.add_argument("--target", choices=["flask", "fastapi", "both"], default="both")
    p.add_argument("--concurrency", type=int, default=5)
    p.add_argument("--endpoint", choices=["agent", "rates", "health"],
                   default="rates",
                   help="agent=streaming /api/agent (slow); rates=cheap SQL; health=cheapest")
    p.add_argument("--flask-url", default="http://127.0.0.1:8080")
    p.add_argument("--fastapi-url", default="http://127.0.0.1:8082")
    args = p.parse_args()

    targets = []
    if args.target in ("flask", "both"):
        targets.append(("Flask sync (port 8080)", args.flask_url))
    if args.target in ("fastapi", "both"):
        targets.append(("FastAPI async (port 8082)", args.fastapi_url))

    print("=" * 70)
    print(f" Concurrency benchmark — {args.concurrency} concurrent /api/{args.endpoint} calls")
    print("=" * 70)

    results = []
    for label, base in targets:
        print(f"\n--- {label} ---")
        try:
            # health check first
            async with httpx.AsyncClient() as c:
                h = await c.get(f"{base}/api/health", timeout=5)
                print(f"   [health]: {h.status_code}")
            r = await run_bench(base, args.concurrency, DEFAULT_QUERIES, args.endpoint)
            r["label"] = label
            results.append(r)
        except Exception as e:
            print(f"   server unreachable: {e}")

    print("\n" + "=" * 70)
    print(" Results")
    print("=" * 70)
    print(f"{'Server':30s} {'Wall (s)':>10s} {'OK':>4s} {'mean':>7s} {'p95':>7s} {'QPS':>6s}")
    print("-" * 70)
    for r in results:
        print(f"{r['label']:30s} {r['wall_sec']:>10.2f} "
              f"{r['n_ok']:>4d} {r['mean_sec']:>7.2f} "
              f"{r['p95_sec']:>7.2f} {r['qps']:>6.2f}")

    if len(results) == 2 and results[1]["wall_sec"] > 0:
        flask_w = results[0]["wall_sec"]
        fastapi_w = results[1]["wall_sec"]
        if fastapi_w > 0:
            speedup = flask_w / fastapi_w
            print(f"\n→ FastAPI wall-time speedup: {speedup:.2f}× over Flask")
        if results[1]["qps"] > 0:
            qps_ratio = results[1]["qps"] / results[0]["qps"] if results[0]["qps"] else 0
            print(f"→ FastAPI effective QPS: {qps_ratio:.2f}× Flask's")


if __name__ == "__main__":
    asyncio.run(main())
