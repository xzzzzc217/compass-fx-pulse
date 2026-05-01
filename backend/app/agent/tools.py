"""Tool registry for the CompassFX Function Calling Agent.

Each tool has:
  - schema:    OpenAI function-calling JSON schema
  - handler:   Python callable that executes the tool

The router LLM picks tools by name; the executor invokes the handler with
validated arguments and returns a JSON-serialisable result.
"""
from __future__ import annotations

import math
from datetime import date, datetime, timedelta
from typing import Any, Callable

from ..cache import cached_execute
from ..db import get_cursor
from ..rag.pipeline import retrieve as rag_retrieve

# ---------- Tool implementations ----------


def _get_exchange_rate(currency_a: str, currency_b: str,
                       on_date: str | None = None) -> dict:
    """Latest known rate, or rate on a specific date if provided."""
    with get_cursor() as cur:
        if on_date:
            cur.execute(
                """SELECT time, rate FROM historicaldata
                   WHERE currencytype1=%s AND currencytype2=%s AND DATE(time)=%s
                   LIMIT 1""",
                (currency_a, currency_b, on_date),
            )
            row = cur.fetchone()
            if row:
                return {"currency_a": currency_a, "currency_b": currency_b,
                        "date": row[0].strftime("%Y-%m-%d"), "rate": float(row[1])}
            # fall back: closest prior date
            cur.execute(
                """SELECT time, rate FROM historicaldata
                   WHERE currencytype1=%s AND currencytype2=%s AND DATE(time)<=%s
                   ORDER BY time DESC LIMIT 1""",
                (currency_a, currency_b, on_date),
            )
            row = cur.fetchone()
            if row:
                return {"currency_a": currency_a, "currency_b": currency_b,
                        "date": row[0].strftime("%Y-%m-%d"), "rate": float(row[1]),
                        "note": "exact date not found, returning closest prior"}
            return {"error": f"no data for {currency_a}/{currency_b} on or before {on_date}"}

        cur.execute(
            """SELECT time, rate FROM historicaldata
               WHERE currencytype1=%s AND currencytype2=%s
               ORDER BY time DESC LIMIT 1""",
            (currency_a, currency_b),
        )
        row = cur.fetchone()
    if not row:
        return {"error": f"no data for {currency_a}/{currency_b}"}
    return {"currency_a": currency_a, "currency_b": currency_b,
            "date": row[0].strftime("%Y-%m-%d"), "rate": float(row[1])}


def _get_rate_range(currency_a: str, currency_b: str,
                    start_date: str, end_date: str) -> dict:
    with get_cursor() as cur:
        cur.execute(
            """SELECT DATE(time), rate FROM historicaldata
               WHERE currencytype1=%s AND currencytype2=%s
                 AND time BETWEEN %s AND %s
               ORDER BY time""",
            (currency_a, currency_b, start_date, end_date),
        )
        rows = cur.fetchall()
    if not rows:
        return {"error": f"no data in range", "currency_a": currency_a,
                "currency_b": currency_b, "start": start_date, "end": end_date}

    rates = [float(r[1]) for r in rows]
    return {
        "currency_a": currency_a, "currency_b": currency_b,
        "start": start_date, "end": end_date,
        "n_days": len(rows),
        "first": {"date": rows[0][0].isoformat(), "rate": rates[0]},
        "last": {"date": rows[-1][0].isoformat(), "rate": rates[-1]},
        "min": min(rates), "max": max(rates),
        "mean": sum(rates) / len(rates),
        "stdev": _stdev(rates),
        "change_pct": (rates[-1] - rates[0]) / rates[0] * 100 if rates[0] else None,
    }


def _predict_rate(currency_a: str, currency_b: str, horizon_days: int = 30) -> dict:
    with get_cursor() as cur:
        cur.execute(
            """SELECT DATE(time), rate FROM predictdata
               WHERE currencytype1=%s AND currencytype2=%s
               ORDER BY time LIMIT %s""",
            (currency_a, currency_b, horizon_days),
        )
        rows = cur.fetchall()
    if not rows:
        return {"error": "no prediction data available — run seed_predictions.py "
                         "or wait for TimeXer integration"}
    rates = [float(r[1]) for r in rows]
    return {
        "currency_a": currency_a, "currency_b": currency_b,
        "horizon_days": len(rows),
        "first_date": rows[0][0].isoformat(),
        "last_date": rows[-1][0].isoformat(),
        "mean_predicted": sum(rates) / len(rates),
        "min_predicted": min(rates),
        "max_predicted": max(rates),
        "trajectory": [{"date": r[0].isoformat(), "rate": float(r[1])}
                       for r in rows],
        "model_note": "SARIMAX(1,1,1)(1,0,1,5) sampled trajectory. "
                      "Refresh via: python backend/scripts/predict_rates.py",
    }


def _calculate_var(currency_a: str, currency_b: str,
                   position_amount: float,
                   confidence: float = 0.99,
                   horizon_days: int = 1,
                   lookback_days: int = 252) -> dict:
    """Parametric (delta-normal) VaR using historical volatility."""
    end = date.today()
    start = end - timedelta(days=int(lookback_days * 1.5))  # cushion for weekends/holidays

    with get_cursor() as cur:
        cur.execute(
            """SELECT rate FROM historicaldata
               WHERE currencytype1=%s AND currencytype2=%s
                 AND time BETWEEN %s AND %s
               ORDER BY time""",
            (currency_a, currency_b, start, end),
        )
        rates = [float(r[0]) for r in cur.fetchall()]

    if len(rates) < 30:
        return {"error": f"insufficient history ({len(rates)} days), need ≥30"}

    # log returns
    rets = [math.log(rates[i] / rates[i - 1]) for i in range(1, len(rates))]
    sigma = _stdev(rets)
    # z-score for one-sided confidence
    z = {0.90: 1.282, 0.95: 1.645, 0.99: 2.326}.get(round(confidence, 2), 2.326)

    one_day_var_ret = z * sigma
    horizon_var_ret = one_day_var_ret * math.sqrt(horizon_days)
    var_amount = abs(position_amount) * horizon_var_ret

    return {
        "currency_a": currency_a, "currency_b": currency_b,
        "position_amount": position_amount,
        "confidence": confidence,
        "horizon_days": horizon_days,
        "daily_volatility_pct": sigma * 100,
        f"VaR_{int(confidence*100)}_{horizon_days}d": var_amount,
        "interpretation": f"在{int(confidence*100)}%置信度下，{horizon_days}天内"
                          f"该敞口最大可能损失约 {var_amount:.2f} {currency_b}",
        "method": "delta-normal (parametric)",
        "lookback_days": len(rates),
    }


def _stdev(xs: list[float]) -> float:
    if len(xs) < 2:
        return 0.0
    m = sum(xs) / len(xs)
    return math.sqrt(sum((x - m) ** 2 for x in xs) / (len(xs) - 1))


def _search_knowledge(query: str, k: int = 5,
                      currency: str | None = None,
                      category: str | None = None) -> dict:
    """RAG: dense + rerank, return top-k passages with citations."""
    where = None
    filters = {}
    if currency:
        filters["currency"] = currency
    if category:
        filters["category"] = category
    if filters:
        where = filters if len(filters) == 1 else {"$and": [{k: v} for k, v in filters.items()]}

    try:
        hits = rag_retrieve(query, k=k, where=where)
    except Exception as exc:
        return {"error": f"RAG retrieval failed: {exc}",
                "hint": "Run 'python scripts/rebuild_rag.py --rebuild' to build the index."}

    if not hits:
        return {"results": [], "n": 0,
                "note": "no relevant passages found above the rerank threshold"}

    return {
        "n": len(hits),
        "results": [
            {
                "title": h.get("title") or h.get("source_file"),
                "category": h.get("category"),
                "currency": h.get("currency") or None,
                "rerank_score": round(h.get("rerank_score", 0.0), 3),
                "text": h["text"],
                "source_file": h.get("source_file"),
            }
            for h in hits
        ],
    }


# ---------- Schema definitions ----------

TOOLS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "get_exchange_rate",
            "description": "Look up a real exchange rate from the database. "
                           "USE WHEN: user asks 'what is the rate today / on YYYY-MM-DD'. "
                           "DO NOT USE for: educational examples, definitions, "
                           "'what is X' questions — those should be answered from "
                           "your own knowledge with hypothetical numbers.",
            "parameters": {
                "type": "object",
                "properties": {
                    "currency_a": {"type": "string", "enum": ["USD", "EUR", "GBP", "JPY", "HKD", "AUD"]},
                    "currency_b": {"type": "string", "enum": ["USD", "EUR", "GBP", "JPY", "HKD", "AUD"]},
                    "on_date": {"type": "string",
                                "description": "YYYY-MM-DD; omit for latest available"},
                },
                "required": ["currency_a", "currency_b"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_rate_range",
            "description": "Compute statistics (min/max/mean/stdev/change%) over a "
                           "date range from real database data. "
                           "USE WHEN: user asks for stats over a specific period. "
                           "DO NOT USE for: conceptual questions about volatility "
                           "('what is volatility?').",
            "parameters": {
                "type": "object",
                "properties": {
                    "currency_a": {"type": "string", "enum": ["USD", "EUR", "GBP", "JPY", "HKD", "AUD"]},
                    "currency_b": {"type": "string", "enum": ["USD", "EUR", "GBP", "JPY", "HKD", "AUD"]},
                    "start_date": {"type": "string", "description": "YYYY-MM-DD"},
                    "end_date": {"type": "string", "description": "YYYY-MM-DD"},
                },
                "required": ["currency_a", "currency_b", "start_date", "end_date"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "predict_exchange_rate",
            "description": "Forecast a currency pair for the next N days. "
                           "Uses placeholder model in Phase 0; TimeXer in Phase 2.",
            "parameters": {
                "type": "object",
                "properties": {
                    "currency_a": {"type": "string", "enum": ["USD", "EUR", "GBP", "JPY", "HKD", "AUD"]},
                    "currency_b": {"type": "string", "enum": ["USD", "EUR", "GBP", "JPY", "HKD", "AUD"]},
                    "horizon_days": {"type": "integer", "minimum": 1, "maximum": 90,
                                     "default": 30},
                },
                "required": ["currency_a", "currency_b"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_forex_knowledge",
            "description": "Search the curated forex knowledge base (currency profiles, "
                           "concepts like CIP/UIP/VaR, risk management, central-bank policy). "
                           "USE WHEN: the question is about *concepts*, *mechanisms*, "
                           "*central-bank policy*, *historical examples*, or *how things work* "
                           "— and you want to ground your answer in our curated corpus instead of "
                           "training data. "
                           "DO NOT USE for: queries that need a specific real number "
                           "(rate, prediction, VaR figure) — those belong to other tools.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string",
                              "description": "Search query in Chinese or English"},
                    "k": {"type": "integer", "minimum": 1, "maximum": 10, "default": 5,
                          "description": "Number of passages to return (after rerank)"},
                    "currency": {"type": "string",
                                 "enum": ["USD", "EUR", "GBP", "JPY", "HKD", "AUD"],
                                 "description": "Optional metadata filter"},
                    "category": {"type": "string",
                                 "enum": ["currency", "concept", "risk", "policy"],
                                 "description": "Optional metadata filter"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "calculate_var",
            "description": "Compute actual VaR for a specific FX exposure using "
                           "historical volatility. "
                           "USE WHEN: user gives a concrete position size and asks "
                           "for the VaR number. "
                           "DO NOT USE for: 'what is VaR' / 'how does VaR work' — "
                           "those are educational questions, answer from knowledge.",
            "parameters": {
                "type": "object",
                "properties": {
                    "currency_a": {"type": "string", "enum": ["USD", "EUR", "GBP", "JPY", "HKD", "AUD"]},
                    "currency_b": {"type": "string", "enum": ["USD", "EUR", "GBP", "JPY", "HKD", "AUD"]},
                    "position_amount": {"type": "number",
                                        "description": "Notional exposure in currency_a"},
                    "confidence": {"type": "number", "enum": [0.90, 0.95, 0.99],
                                   "default": 0.99},
                    "horizon_days": {"type": "integer", "minimum": 1, "maximum": 30,
                                     "default": 1},
                    "lookback_days": {"type": "integer", "minimum": 30, "default": 252},
                },
                "required": ["currency_a", "currency_b", "position_amount"],
            },
        },
    },
]

HANDLERS: dict[str, Callable[..., dict]] = {
    "get_exchange_rate": _get_exchange_rate,
    "get_rate_range": _get_rate_range,
    "predict_exchange_rate": _predict_rate,
    "calculate_var": _calculate_var,
    "search_forex_knowledge": _search_knowledge,
}


def execute(name: str, args: dict[str, Any], use_cache: bool = True) -> dict:
    """Execute a tool by name.

    Phase 4.1: results are TTL-cached (per-tool TTL in app.cache.TOOL_TTL).
    Pass use_cache=False for fresh data (e.g. when the user explicitly
    asks for "real-time").
    """
    if name not in HANDLERS:
        return {"error": f"unknown tool: {name}"}
    try:
        if use_cache:
            return cached_execute(name, args, HANDLERS[name])
        return HANDLERS[name](**args)
    except TypeError as exc:
        return {"error": f"argument error: {exc}"}
    except Exception as exc:
        return {"error": f"execution error: {type(exc).__name__}: {exc}"}
