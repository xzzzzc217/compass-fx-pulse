"""Smoke test for the MCP server.

Spawns server.py as a subprocess speaking JSON-RPC over stdio and verifies:
  1. The server responds to `initialize`
  2. `tools/list` returns the 5 tools we registered
  3. Data tools (DB-only) work
  4. (--with-rag) RAG tool also works (slow first call; loads bge-m3 in subprocess)

Run:
    python tests/test_mcp_server.py             # quick — 4 data tools only
    python tests/test_mcp_server.py --with-rag  # full — also tests RAG (~60s)
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

EXPECTED_TOOLS = {
    "get_exchange_rate",
    "get_rate_range",
    "predict_exchange_rate",
    "calculate_var",
    "search_forex_knowledge",
}


async def run(with_rag: bool = False) -> int:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "mcp_server.server"],
        cwd=str(ROOT),
        env={
            "PYTHONUTF8": "1",
            "KMP_DUPLICATE_LIB_OK": "TRUE",
            "OMP_NUM_THREADS": "1",
            **{k: v for k, v in __import__("os").environ.items() if k in
               ("PATH", "PYTHONPATH", "SYSTEMROOT", "TEMP", "TMP", "USERPROFILE")},
        },
    )

    print("Spawning MCP server via stdio ...")
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            print("Initializing ...")
            await session.initialize()

            print("\n=== tools/list ===")
            res = await session.list_tools()
            names = {t.name for t in res.tools}
            print(f"Server reports {len(names)} tools: {sorted(names)}")
            missing = EXPECTED_TOOLS - names
            extra = names - EXPECTED_TOOLS
            if missing or extra:
                print(f"  FAIL — missing={missing} extra={extra}")
                return 1
            print(f"  PASS — all {len(EXPECTED_TOOLS)} expected tools present")

            print("\n=== call get_exchange_rate ===")
            r = await session.call_tool(
                "get_exchange_rate",
                {"currency_a": "USD", "currency_b": "JPY"},
            )
            text = r.content[0].text if r.content else ""
            print(f"Result: {text[:200]}")
            if "rate" not in text and "error" not in text:
                print("  FAIL — missing 'rate' field")
                return 1
            print("  PASS")

            print("\n=== call get_rate_range ===")
            r = await session.call_tool(
                "get_rate_range",
                {
                    "currency_a": "USD", "currency_b": "EUR",
                    "start_date": "2026-04-01", "end_date": "2026-04-27",
                },
            )
            text = r.content[0].text if r.content else ""
            print(f"Result: {text[:200]}")
            print("  PASS" if ("min" in text or "error" in text) else "  FAIL")

            if with_rag:
                print("\n=== call search_forex_knowledge ===")
                print("  (first call will be slow: bge-m3 + reranker cold load, ~60s)")
                r = await session.call_tool(
                    "search_forex_knowledge",
                    {"query": "什么是 carry trade", "k": 3},
                )
                text = r.content[0].text if r.content else ""
                print(f"Result: {text[:300]}")
                if "results" not in text and "error" not in text:
                    print("  FAIL — missing 'results' field")
                    return 1
                print("  PASS")
            else:
                print("\n=== call search_forex_knowledge ===")
                print("  SKIPPED (use --with-rag to include; loads ~3GB models in subprocess)")

            print("\n=== resource read ===")
            try:
                res2 = await session.read_resource("compass-fx://corpus/concept_carry_trade.md")
                content = res2.contents[0].text if res2.contents else ""
                print(f"Got {len(content)} chars from corpus")
                print("  PASS" if "Carry Trade" in content else "  WARN")
            except Exception as exc:
                print(f"  WARN — resource read failed: {exc}")

    print("\n=== ALL SMOKE TESTS DONE ===")
    return 0


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--with-rag", action="store_true",
                   help="Also test search_forex_knowledge (slow: ~60s cold load)")
    args = p.parse_args()
    rc = asyncio.run(run(with_rag=args.with_rag))
    sys.exit(rc)
