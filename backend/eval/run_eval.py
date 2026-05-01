"""Phase 4.2 — run the full eval suite and produce a markdown report.

Usage:
    cd backend
    python eval/run_eval.py --suite full
    python eval/run_eval.py --suite no-cache       # ablation: bypass cache
    python eval/run_eval.py --suite full --limit 5  # sanity check on 5 questions
    python eval/run_eval.py --suite full --skip-judge  # rule-only (free, fast)
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# ===== Windows + PyTorch hardening (must precede torch / transformers imports) =====
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")

from eval.judge import JudgeClient
from eval.runner import run_direct
from eval.scoring import aggregate, composite_pass, rule_based_score


def load_golden_set(path: Path) -> list[dict]:
    cases = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("//"):
                continue
            cases.append(json.loads(line))
    return cases


def run_one(case: dict, judge: JudgeClient | None,
            disable_cache: bool = False) -> dict:
    print(f"  [{case['id']:3s}] {case['query'][:50]}", flush=True)

    # Cache bypass: clear the global cache before each call
    if disable_cache:
        from app.cache import clear as cache_clear
        cache_clear()

    try:
        run = run_direct(case["query"])
    except Exception as e:
        return {
            "id": case["id"],
            "category": case["category"],
            "query": case["query"],
            "pass": False,
            "rule": {"tool_correct": False, "tool_called": [],
                     "tool_expected": case.get("expect_tools", []),
                     "keyword_score": 0.0},
            "judge": {"accuracy": 0, "faithfulness": 0, "helpfulness": 0,
                      "issues": f"runner exception: {e}"},
            "latency_ms": 0,
            "text": "",
            "error": str(e),
        }

    rule = rule_based_score(case, run)

    if judge is None:
        verdict = {"accuracy": 0, "faithfulness": 0, "helpfulness": 0,
                   "issues": "judge skipped"}
    else:
        verdict = judge.score(case["query"], run)

    record = {
        "id": case["id"],
        "category": case["category"],
        "query": case["query"],
        "rule": rule,
        "judge": verdict,
        "latency_ms": run.get("latency_ms", 0),
        "tools_called": [tc["name"] for tc in run.get("tools_called", [])],
        "text": run.get("text", "")[:500],
        "errors": run.get("errors", []),
    }
    record["pass"] = composite_pass(rule, verdict) if judge else (
        rule["tool_correct"] and rule["keyword_score"] >= 0.5
    )
    status = "PASS" if record["pass"] else "FAIL"
    j = verdict
    print(f"      [{status}] tool={rule['tool_correct']!s:5s} kw={rule['keyword_score']:.2f} "
          f"acc={j['accuracy']} faith={j['faithfulness']} help={j['helpfulness']} "
          f"({record['latency_ms']:.0f}ms)", flush=True)
    return record


def write_report(suite: str, results: list[dict], summary: dict, out_dir: Path) -> Path:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    md_path = out_dir / f"eval_{ts}_{suite}.md"
    jsonl_path = out_dir / f"eval_{ts}_{suite}.jsonl"

    # JSONL: per-case raw
    with open(jsonl_path, "w", encoding="utf-8") as f:
        for r in results:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    # Markdown: summary
    lines = [
        f"# Eval Report — suite=`{suite}` ({ts})",
        "",
        f"**Total**: {summary['total']} questions",
        f"**Pass rate**: {summary['pass']}/{summary['total']} = **{summary['pass_rate']:.1%}**",
        "",
        "## Aggregate metrics",
        "",
        "| Metric | Value |",
        "|---|---|",
        f"| Tool routing accuracy | {summary['tool_routing_accuracy']:.1%} |",
        f"| Avg keyword score | {summary['avg_keyword_score']:.2f} |",
        f"| Avg judge accuracy (1-10) | {summary['avg_judge_accuracy']:.2f} |",
        f"| Avg judge faithfulness (1-10) | {summary['avg_judge_faithfulness']:.2f} |",
        f"| Avg judge helpfulness (1-10) | {summary['avg_judge_helpfulness']:.2f} |",
        f"| Avg latency (ms) | {summary['avg_latency_ms']:.0f} |",
        f"| P95 latency (ms) | {summary['p95_latency_ms']:.0f} |",
        "",
        "## Per-category breakdown",
        "",
        "| Category | N | Pass rate | Tool routing | Avg acc | Avg faith | Avg help |",
        "|---|---|---|---|---|---|---|",
    ]
    for cat, d in sorted(summary["by_category"].items()):
        lines.append(
            f"| {cat} | {d['n']} | {d['pass_rate']:.1%} | "
            f"{d['tool_routing_acc']:.1%} | {d['avg_acc']:.2f} | "
            f"{d['avg_faith']:.2f} | {d['avg_help']:.2f} |"
        )

    lines += ["", "## Failed cases", ""]
    fails = [r for r in results if not r["pass"]]
    if not fails:
        lines.append("(none)")
    else:
        for r in fails:
            lines += [
                f"### {r['id']} ({r['category']})",
                f"**Q**: {r['query']}",
                f"**Expected tools**: {r['rule']['tool_expected']}",
                f"**Called tools**: {r['rule']['tool_called']}",
                f"**Keyword score**: {r['rule']['keyword_score']}",
                f"**Judge**: acc={r['judge']['accuracy']}, "
                f"faith={r['judge']['faithfulness']}, help={r['judge']['helpfulness']}",
                f"**Issue**: {r['judge'].get('issues', 'n/a')}",
                f"**Answer (preview)**: {r['text'][:300]}",
                "",
            ]

    with open(md_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    return md_path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--suite", default="full",
                        choices=["full", "no-cache"],
                        help="full = production system; no-cache = bypass cache")
    parser.add_argument("--limit", type=int, default=0,
                        help="run only N questions (sanity check)")
    parser.add_argument("--skip-judge", action="store_true",
                        help="rule-based only; no LLM-as-Judge calls (free)")
    parser.add_argument("--golden-set", default=None,
                        help="path to golden_set.jsonl (default: eval/golden_set.jsonl)")
    args = parser.parse_args()

    eval_dir = Path(__file__).resolve().parent
    gs_path = Path(args.golden_set) if args.golden_set else eval_dir / "golden_set.jsonl"
    out_dir = eval_dir / "results"
    out_dir.mkdir(parents=True, exist_ok=True)

    cases = load_golden_set(gs_path)
    if args.limit > 0:
        cases = cases[:args.limit]

    print(f"=== CompassFX Eval — suite={args.suite}, n={len(cases)}, "
          f"judge={'no' if args.skip_judge else 'yes'} ===\n")

    judge = None if args.skip_judge else JudgeClient()

    t0 = time.time()
    results = []
    for case in cases:
        results.append(run_one(case, judge, disable_cache=(args.suite == "no-cache")))
    total_elapsed = time.time() - t0

    summary = aggregate(results)
    print(f"\n=== Done in {total_elapsed:.1f}s ===")
    print(f"Pass: {summary['pass']}/{summary['total']} ({summary['pass_rate']:.1%})")
    print(f"Tool routing acc: {summary['tool_routing_accuracy']:.1%}")
    if not args.skip_judge:
        print(f"Avg judge acc/faith/help: "
              f"{summary['avg_judge_accuracy']:.1f} / "
              f"{summary['avg_judge_faithfulness']:.1f} / "
              f"{summary['avg_judge_helpfulness']:.1f}")
    print(f"Latency: avg={summary['avg_latency_ms']:.0f}ms, "
          f"p95={summary['p95_latency_ms']:.0f}ms")

    md_path = write_report(args.suite, results, summary, out_dir)
    print(f"\nReport: {md_path}")


if __name__ == "__main__":
    main()
