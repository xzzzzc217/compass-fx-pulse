"""Smoke tests for the Function Calling Agent.

Hits the live backend at http://127.0.0.1:8080/api/agent and checks that
the agent actually invokes tools rather than hallucinating numbers.

Usage (with backend running):
    python tests/test_agent.py
    python tests/test_agent.py --base http://127.0.0.1:8080

Test cases cover:
  1. Latest rate query → should call get_exchange_rate
  2. Range stats query → should call get_rate_range
  3. Pure knowledge question → should NOT call any tool
  4. VaR calculation → should call calculate_var
  5. Prediction → should call predict_exchange_rate
"""
from __future__ import annotations

import argparse
import json
import sys
from urllib.parse import quote

import requests

CASES = [
    {
        "name": "latest rate",
        "query": "现在美元兑日元的汇率是多少？",
        "expect_tool": "get_exchange_rate",
        "expect_no_tool": False,
    },
    {
        "name": "range stats",
        "query": "美元兑欧元在 2026 年 4 月的最大、最小、平均汇率分别是多少？",
        "expect_tool": "get_rate_range",
        "expect_no_tool": False,
    },
    {
        "name": "concept question (long form, RAG path)",
        "query": "什么是 carry trade？请解释机制。",
        "expect_tool": "search_forex_knowledge",
        "expect_no_tool": False,  # Phase 3+: concepts route to RAG
    },
    {
        "name": "concept question (short)",
        "query": "什么是 carry trade？",
        "expect_tool": "search_forex_knowledge",
        "expect_no_tool": False,
    },
    {
        "name": "off-topic chatter (no tool)",
        "query": "今天天气怎么样？",
        "expect_tool": None,
        "expect_no_tool": True,  # off-topic = no tool
    },
    {
        "name": "concept question (definition)",
        "query": "VaR 是什么意思？",
        "expect_tool": "search_forex_knowledge",
        "expect_no_tool": False,  # should hit RAG, not calculate_var
    },
    {
        "name": "RAG: policy primer",
        "query": "美联储 FOMC 的决策框架是什么？",
        "expect_tool": "search_forex_knowledge",
        "expect_no_tool": False,
    },
    {
        "name": "RAG: concept with currency context",
        "query": "请解释 carry trade 在日元上的典型应用",
        "expect_tool": "search_forex_knowledge",
        "expect_no_tool": False,
    },
    {
        "name": "VaR calculation",
        "query": "我有 100 万美元的美元/日元敞口，1 天 99% VaR 是多少？",
        "expect_tool": "calculate_var",
        "expect_no_tool": False,
    },
    {
        "name": "prediction",
        "query": "预测未来 30 天的欧元/美元走势",
        "expect_tool": "predict_exchange_rate",
        "expect_no_tool": False,
    },
]


def parse_sse(stream) -> dict:
    """Collect text and trace events from SSE stream."""
    text_parts = []
    tools_called = []
    plans = []
    for raw in stream.iter_lines():
        if not raw:
            continue
        line = raw.decode("utf-8")
        if not line.startswith("data: "):
            continue
        try:
            obj = json.loads(line[6:])
        except json.JSONDecodeError:
            continue
        if "trace" in obj:
            tr = obj["trace"]
            if tr["kind"] == "plan":
                plans.append(tr["tools"])
            elif tr["kind"] == "tool_result":
                tools_called.append({
                    "name": tr["name"], "args": tr.get("args", {}),
                    "result_preview": str(tr.get("result", ""))[:200],
                })
        elif "text" in obj:
            t = obj["text"]
            if t == "[DONE]" or t.startswith("[ERROR]"):
                continue
            text_parts.append(t)
    return {
        "text": "".join(text_parts),
        "tools_called": tools_called,
        "plans": plans,
    }


def run_case(base: str, case: dict) -> bool:
    print(f"\n=== {case['name']} ===")
    print(f"Q: {case['query']}")
    url = f"{base}/api/agent?query={quote(case['query'])}&trace=1"
    with requests.get(url, stream=True, timeout=120) as resp:
        if resp.status_code != 200:
            print(f"  HTTP {resp.status_code}: {resp.text[:200]}")
            return False
        result = parse_sse(resp)

    print(f"  Plans: {result['plans']}")
    for tc in result["tools_called"]:
        print(f"  Tool: {tc['name']}({tc['args']})")
        print(f"        → {tc['result_preview']}")
    print(f"  Final text ({len(result['text'])} chars): {result['text'][:300]}")

    # Pass / fail logic
    if case["expect_no_tool"]:
        passed = len(result["tools_called"]) == 0
        verdict = "PASS (no tool call as expected)" if passed else "FAIL (unexpected tool call)"
    else:
        names = [tc["name"] for tc in result["tools_called"]]
        passed = case["expect_tool"] in names
        verdict = (f"PASS (called {case['expect_tool']})" if passed
                   else f"FAIL (expected {case['expect_tool']}, got {names})")
    print(f"  ▶ {verdict}")
    return passed


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--base", default="http://127.0.0.1:8080")
    args = p.parse_args()

    # health check first
    try:
        h = requests.get(f"{args.base}/api/health", timeout=5).json()
        print(f"Health: {h}")
    except Exception as exc:
        print(f"Backend not reachable at {args.base}: {exc}")
        sys.exit(1)

    passed = sum(run_case(args.base, c) for c in CASES)
    total = len(CASES)
    print(f"\n=== Results: {passed}/{total} passed ===")
    sys.exit(0 if passed == total else 1)


if __name__ == "__main__":
    main()
