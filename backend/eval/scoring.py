"""Phase 4.2 — combine rule-based + LLM-as-Judge into final pass/fail + scores."""
from __future__ import annotations

from typing import Any


def rule_based_score(case: dict, run: dict) -> dict:
    """Rule-based checks: tool routing + keyword presence + refusal correctness."""
    tools_called_names = [tc["name"] for tc in run.get("tools_called", [])]
    text = run.get("text", "")

    # Tool routing check
    expected_tools = case.get("expect_tools", [])
    must_call = case.get("must_call_tool", False)
    must_refuse = case.get("must_refuse", False)

    if must_refuse:
        # Refusal: should NOT call any tool
        tool_correct = len(tools_called_names) == 0
    elif must_call:
        # Must hit at least one of the expected tools
        if expected_tools:
            tool_correct = any(t in tools_called_names for t in expected_tools)
        else:
            tool_correct = len(tools_called_names) > 0
    else:
        # Chitchat: should NOT call tools
        tool_correct = len(tools_called_names) == 0

    # Keyword check (all-required vs any-required)
    keyword_score = 1.0
    if "expect_keywords" in case:
        kws = case["expect_keywords"]
        hits = sum(1 for kw in kws if kw.lower() in text.lower())
        keyword_score = hits / len(kws) if kws else 1.0
    elif "expect_keywords_any" in case:
        kws = case["expect_keywords_any"]
        keyword_score = 1.0 if any(kw.lower() in text.lower() for kw in kws) else 0.0

    return {
        "tool_correct": tool_correct,
        "tool_called": tools_called_names,
        "tool_expected": expected_tools,
        "keyword_score": round(keyword_score, 2),
    }


def composite_pass(rule: dict, judge: dict) -> bool:
    """A case 'passes' if:
       1. Tool routing was correct (or chitchat with no tools)
       2. Keyword score >= 0.5
       3. Judge accuracy >= 6
    """
    if not rule["tool_correct"]:
        return False
    if rule["keyword_score"] < 0.5:
        return False
    if judge.get("accuracy", 0) < 6:
        return False
    return True


def aggregate(case_results: list[dict]) -> dict:
    """Roll up per-case scores into a suite-level summary."""
    if not case_results:
        return {}

    n = len(case_results)
    pass_count = sum(1 for r in case_results if r["pass"])
    tool_correct = sum(1 for r in case_results if r["rule"]["tool_correct"])
    avg_kw = sum(r["rule"]["keyword_score"] for r in case_results) / n
    avg_acc = sum(r["judge"]["accuracy"] for r in case_results) / n
    avg_faith = sum(r["judge"]["faithfulness"] for r in case_results) / n
    avg_help = sum(r["judge"]["helpfulness"] for r in case_results) / n
    avg_lat = sum(r["latency_ms"] for r in case_results) / n
    p95_lat = sorted(r["latency_ms"] for r in case_results)[int(n * 0.95) if n > 1 else 0]

    # Per-category breakdown
    by_cat: dict[str, dict] = {}
    for r in case_results:
        cat = r["category"]
        d = by_cat.setdefault(cat, {"n": 0, "pass": 0, "tool_correct": 0,
                                    "acc": 0.0, "faith": 0.0, "help": 0.0})
        d["n"] += 1
        d["pass"] += int(r["pass"])
        d["tool_correct"] += int(r["rule"]["tool_correct"])
        d["acc"] += r["judge"]["accuracy"]
        d["faith"] += r["judge"]["faithfulness"]
        d["help"] += r["judge"]["helpfulness"]

    for cat, d in by_cat.items():
        c_n = d["n"]
        d["pass_rate"] = round(d["pass"] / c_n, 2)
        d["tool_routing_acc"] = round(d["tool_correct"] / c_n, 2)
        d["avg_acc"] = round(d["acc"] / c_n, 2)
        d["avg_faith"] = round(d["faith"] / c_n, 2)
        d["avg_help"] = round(d["help"] / c_n, 2)
        for k in ("acc", "faith", "help"):
            d.pop(k)
        d.pop("pass")
        d.pop("tool_correct")

    return {
        "total": n,
        "pass": pass_count,
        "pass_rate": round(pass_count / n, 3),
        "tool_routing_accuracy": round(tool_correct / n, 3),
        "avg_keyword_score": round(avg_kw, 2),
        "avg_judge_accuracy": round(avg_acc, 2),
        "avg_judge_faithfulness": round(avg_faith, 2),
        "avg_judge_helpfulness": round(avg_help, 2),
        "avg_latency_ms": round(avg_lat, 0),
        "p95_latency_ms": round(p95_lat, 0),
        "by_category": by_cat,
    }
