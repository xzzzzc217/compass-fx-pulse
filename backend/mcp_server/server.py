"""CompassFX MCP Server.

Exposes the same 5 tools that the Function Calling Agent uses, but via the
Model Context Protocol — so Cursor / Claude Desktop / any MCP-aware client
can call them without going through our Flask Agent.

Two transports:
  - stdio (default) — for local clients like Claude Desktop / Cursor
  - http  — for remote / cross-machine integration

Run:
    python -m mcp_server.server                # stdio
    python -m mcp_server.server --http 9001    # SSE on :9001

Tools (auto-discovered from app.agent.tools.HANDLERS):
    get_exchange_rate, get_rate_range,
    predict_exchange_rate, calculate_var,
    search_forex_knowledge

The wire schema is generated from the function signatures + docstrings.
Heavy models (bge-m3, bge-reranker) are loaded lazily on first RAG call.
"""
from __future__ import annotations

# Reuse Windows hardening from Flask main
import os
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")

import argparse
import json
import sys
from pathlib import Path
from typing import Optional

# Allow `from app.agent.tools import ...` when running via `python server.py`
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mcp.server.fastmcp import FastMCP  # noqa: E402

from app.agent.tools import execute  # noqa: E402

mcp = FastMCP("compass-fx")


# ============================================================================
# Tool wrappers — thin shells over app/agent/tools.py handlers
#
# Each MCP tool's docstring + type annotations become the schema the LLM sees.
# Keep descriptions identical to what's in the Flask Agent's TOOLS array so
# behaviour is consistent across both entry points.
# ============================================================================

@mcp.tool()
def get_exchange_rate(
    currency_a: str,
    currency_b: str,
    on_date: Optional[str] = None,
) -> str:
    """Look up a real exchange rate from the CompassFX database.

    USE WHEN: user asks "what is the rate today / on YYYY-MM-DD".
    DO NOT USE for: educational / definitional questions.

    Args:
        currency_a: One of USD, EUR, GBP, JPY, HKD, AUD.
        currency_b: One of USD, EUR, GBP, JPY, HKD, AUD.
        on_date: Optional YYYY-MM-DD; omit for latest available.

    Returns:
        JSON string with currency_a, currency_b, date, rate.
    """
    args = {"currency_a": currency_a, "currency_b": currency_b}
    if on_date:
        args["on_date"] = on_date
    return json.dumps(execute("get_exchange_rate", args), ensure_ascii=False)


@mcp.tool()
def get_rate_range(
    currency_a: str,
    currency_b: str,
    start_date: str,
    end_date: str,
) -> str:
    """Aggregate statistics (min/max/mean/stdev/change%) of a pair over a date range.

    USE WHEN: user asks for stats over a specific period.

    Args:
        currency_a: One of USD, EUR, GBP, JPY, HKD, AUD.
        currency_b: One of USD, EUR, GBP, JPY, HKD, AUD.
        start_date: YYYY-MM-DD.
        end_date: YYYY-MM-DD.
    """
    return json.dumps(execute("get_rate_range", {
        "currency_a": currency_a,
        "currency_b": currency_b,
        "start_date": start_date,
        "end_date": end_date,
    }), ensure_ascii=False)


@mcp.tool()
def predict_exchange_rate(
    currency_a: str,
    currency_b: str,
    horizon_days: int = 30,
) -> str:
    """Forecast a currency pair for the next N days.

    Phase 0 uses a placeholder model (rolling mean); Phase 2+ TimeXer.

    Args:
        currency_a: One of USD, EUR, GBP, JPY, HKD, AUD.
        currency_b: One of USD, EUR, GBP, JPY, HKD, AUD.
        horizon_days: 1-90. Default 30.
    """
    return json.dumps(execute("predict_exchange_rate", {
        "currency_a": currency_a,
        "currency_b": currency_b,
        "horizon_days": horizon_days,
    }), ensure_ascii=False)


@mcp.tool()
def calculate_var(
    currency_a: str,
    currency_b: str,
    position_amount: float,
    confidence: float = 0.99,
    horizon_days: int = 1,
    lookback_days: int = 252,
) -> str:
    """Compute parametric (delta-normal) Value-at-Risk for a real FX exposure.

    Uses historical volatility from CompassFX DB.
    USE WHEN: user gives a concrete position size and asks for the VaR number.

    Args:
        currency_a: Position currency (USD, EUR, GBP, JPY, HKD, AUD).
        currency_b: Quote currency (same enum).
        position_amount: Notional exposure in currency_a.
        confidence: 0.90, 0.95, or 0.99. Default 0.99.
        horizon_days: 1-30. Default 1.
        lookback_days: history window for volatility. Default 252.
    """
    return json.dumps(execute("calculate_var", {
        "currency_a": currency_a,
        "currency_b": currency_b,
        "position_amount": position_amount,
        "confidence": confidence,
        "horizon_days": horizon_days,
        "lookback_days": lookback_days,
    }), ensure_ascii=False)


@mcp.tool()
def search_forex_knowledge(
    query: str,
    k: int = 5,
    currency: Optional[str] = None,
    category: Optional[str] = None,
) -> str:
    """Search CompassFX curated forex knowledge base via RAG (bge-m3 + bge-reranker).

    USE WHEN: question is about *concepts*, *mechanisms*, *central-bank policy*,
    *historical examples*, or *how things work*.
    DO NOT USE for: queries needing a real number — use the data tools instead.

    Args:
        query: Search query (CN or EN).
        k: Number of passages after rerank. 1-10. Default 5.
        currency: Optional metadata filter (USD, EUR, GBP, JPY, HKD, AUD).
        category: Optional filter (currency, concept, risk, policy).
    """
    args = {"query": query, "k": k}
    if currency:
        args["currency"] = currency
    if category:
        args["category"] = category
    return json.dumps(execute("search_forex_knowledge", args), ensure_ascii=False)


# ============================================================================
# Resource: serve the corpus markdown files for browsing / preview
# ============================================================================

@mcp.resource("compass-fx://corpus/{filename}")
def read_corpus(filename: str) -> str:
    """Read a single corpus document by filename (e.g. 'concept_carry_trade.md')."""
    from app.rag.config import CORPUS_DIR
    safe = Path(filename).name  # path-traversal guard
    p = CORPUS_DIR / safe
    if not p.exists() or p.suffix != ".md":
        return f"# Not found\n\n{safe} is not in the corpus."
    return p.read_text(encoding="utf-8")


# ============================================================================
# Bootstrap
# ============================================================================

def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--http", type=int, default=None,
                   help="Run as HTTP/SSE on the given port (default: stdio)")
    p.add_argument("--warmup-rag", action="store_true",
                   help="Pre-load bge-m3 + reranker at startup (~30-60s) so the "
                        "first search_forex_knowledge call is instant. Otherwise "
                        "lazy loaded on first call.")
    args = p.parse_args()

    if args.warmup_rag:
        print("[warmup] loading bge-m3 + reranker ...", file=sys.stderr, flush=True)
        from app.rag.embedder import embed_one
        from app.rag.reranker import rerank
        embed_one("warmup")
        rerank("warmup", ["a", "b"])
        print("[warmup] RAG ready", file=sys.stderr, flush=True)

    if args.http:
        # FastMCP > 1.x: use streamable HTTP transport
        mcp.settings.host = "127.0.0.1"
        mcp.settings.port = args.http
        mcp.run(transport="streamable-http")
    else:
        mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
