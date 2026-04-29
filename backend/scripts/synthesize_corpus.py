"""Synthesize a curated forex knowledge corpus using DeepSeek.

Produces ~30 markdown documents in backend/data/rag/corpus/ covering:
  - 6 currency profiles (USD, EUR, GBP, JPY, HKD, AUD)
  - 12 core concepts (carry trade, CIP, UIP, VaR, GARCH, hedging, etc.)
  - 6 risk-management practice documents
  - 6 central-bank policy primers

Each doc has YAML front-matter for metadata-aware retrieval.

Usage:
    python scripts/synthesize_corpus.py            # default: only missing docs
    python scripts/synthesize_corpus.py --force    # regenerate all
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Iterable

from openai import OpenAI

ROOT = Path(__file__).resolve().parent.parent  # backend/
PROJECT = ROOT.parent
ENV = PROJECT / "backend" / ".env"
CORPUS = ROOT / "data" / "rag" / "corpus"

PROMPT = """你是一位资深的外汇市场分析师，请为 CompassFXPulse 知识库撰写一篇主题文档。

主题：{topic}
分类：{category}
建议长度：500-900 字

要求：
1. 用中文撰写，专业、准确，可包含必要的英文术语
2. 结构化：从定义/背景出发，分 2-4 个小节展开机制/工具/案例
3. 涉及具体数据时使用历史区间或假设示例（如"假设利差 2%"），不要写"截至 X 月..."这种实时数值
4. 适合后续被切块嵌入并用于检索回答 "什么是 / 怎么运作 / 影响因素" 类问题
5. 包含至少一个具体例子（机制示意 / 历史案例 / 数值演示均可）

直接输出 markdown 正文（不要 frontmatter），从 # 标题开始。"""


# (filename, topic, category, currency)
DOCS: list[tuple[str, str, str, str | None]] = [
    # Currency profiles
    ("usd_profile.md", "美元（USD）的国际地位、储备货币属性与影响因素", "currency", "USD"),
    ("eur_profile.md", "欧元（EUR）的诞生历史、欧元区结构与汇率特性", "currency", "EUR"),
    ("gbp_profile.md", "英镑（GBP）的金融历史、伦敦金融城地位与脱欧后走势", "currency", "GBP"),
    ("jpy_profile.md", "日元（JPY）的避险属性、carry trade 中的角色与日银政策", "currency", "JPY"),
    ("hkd_profile.md", "港币（HKD）联系汇率制度的历史与现状", "currency", "HKD"),
    ("aud_profile.md", "澳元（AUD）作为大宗商品货币的特征与中澳贸易联动", "currency", "AUD"),
    # Core concepts
    ("concept_carry_trade.md", "Carry Trade 套息交易的机制、风险与典型案例", "concept", None),
    ("concept_cip.md", "Covered Interest Rate Parity (CIP) 的推导与失效条件", "concept", None),
    ("concept_uip.md", "Uncovered Interest Rate Parity (UIP) 的理论与现实偏差（forward premium puzzle）", "concept", None),
    ("concept_var.md", "Value at Risk (VaR) 的三种计算方法与局限", "concept", None),
    ("concept_garch.md", "GARCH 模型在外汇波动率建模中的应用", "concept", None),
    ("concept_ppp.md", "购买力平价（PPP）的绝对版本与相对版本", "concept", None),
    ("concept_iv_smile.md", "外汇期权波动率微笑（vol smile）与风险逆转（risk reversal）", "concept", None),
    ("concept_swap_points.md", "外汇 swap points 的定价机制与套利窗口", "concept", None),
    ("concept_yield_curve.md", "国债收益率曲线对汇率的传导机制", "concept", None),
    ("concept_balance_payments.md", "国际收支平衡表中 BOP 与汇率的双向影响", "concept", None),
    ("concept_intervention.md", "央行外汇干预的工具、信号机制与有效性", "concept", None),
    ("concept_fx_microstructure.md", "外汇市场微观结构：做市商、流动性和点差", "concept", None),
    # Risk management practice
    ("risk_corporate_hedging.md", "跨国企业外汇风险敞口的识别与对冲策略选型", "risk", None),
    ("risk_forward_pricing.md", "远期外汇合约定价与企业财务管理实操", "risk", None),
    ("risk_options_strategies.md", "外汇期权对冲策略：collar / risk reversal / participating forward", "risk", None),
    ("risk_natural_hedging.md", "自然对冲：通过经营本身降低汇率敞口", "risk", None),
    ("risk_var_limit_setting.md", "VaR 限额体系在外汇交易部门的设置与监控", "risk", None),
    ("risk_translation_risk.md", "折算风险（translation risk）的会计处理与对冲考量", "risk", None),
    # Central bank policy primers
    ("policy_fed_framework.md", "美联储货币政策框架：FOMC、点阵图、前瞻指引与对美元的影响", "policy", "USD"),
    ("policy_ecb_framework.md", "欧洲央行的两支柱框架与负利率工具", "policy", "EUR"),
    ("policy_boj_yccz.md", "日本央行 YCC（收益率曲线控制）的退出之路", "policy", "JPY"),
    ("policy_pboc_band.md", "人民币汇率管理：CFETS 指数、中间价机制与浮动区间", "policy", None),
    ("policy_hkma_linked.md", "金管局保卫港币联系汇率的强弱方兑换保证", "policy", "HKD"),
    ("policy_rba_framework.md", "澳联储利率框架与铁矿石价格联动", "policy", "AUD"),
]


def _env() -> dict:
    env = {}
    if ENV.exists():
        for line in ENV.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()
    return env


def _frontmatter(topic: str, category: str, currency: str | None) -> str:
    fm = [
        "---",
        f'title: "{topic}"',
        f'category: {category}',
    ]
    if currency:
        fm.append(f'currency: {currency}')
    fm.append("source: synthesized-by-deepseek")
    fm.append(f"generated: {time.strftime('%Y-%m-%d')}")
    fm.append("---\n")
    return "\n".join(fm)


def _gen(client: OpenAI, model: str, topic: str, category: str) -> str:
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system",
             "content": "你是严谨的金融分析师，专注外汇与汇率。"},
            {"role": "user", "content": PROMPT.format(topic=topic, category=category)},
        ],
        temperature=0.6, max_tokens=2000,
    )
    return resp.choices[0].message.content.strip()


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--force", action="store_true", help="regenerate even if file exists")
    p.add_argument("--max", type=int, default=len(DOCS))
    args = p.parse_args()

    env = _env()
    api_key = env.get("LLM_API_KEY") or os.getenv("LLM_API_KEY")
    base_url = env.get("LLM_BASE_URL", "https://api.deepseek.com/v1")
    model = env.get("LLM_MODEL", "deepseek-chat")
    if not api_key or api_key == "please_fill_in":
        print("ERROR: LLM_API_KEY missing in backend/.env"); sys.exit(1)
    client = OpenAI(api_key=api_key, base_url=base_url)

    CORPUS.mkdir(parents=True, exist_ok=True)
    todo: list[tuple[str, str, str, str | None]] = []
    for fn, topic, cat, ccy in DOCS[: args.max]:
        path = CORPUS / fn
        if path.exists() and not args.force:
            continue
        todo.append((fn, topic, cat, ccy))

    print(f"To generate: {len(todo)} / {len(DOCS)} docs")
    if not todo:
        print("Nothing to do."); return

    for i, (fn, topic, cat, ccy) in enumerate(todo, 1):
        print(f"  [{i}/{len(todo)}] {fn}: {topic[:40]}...", end=" ", flush=True)
        try:
            body = _gen(client, model, topic, cat)
            content = _frontmatter(topic, cat, ccy) + body
            (CORPUS / fn).write_text(content, encoding="utf-8")
            print(f"OK ({len(body)} chars)")
        except Exception as exc:
            print(f"FAIL: {exc}")
        time.sleep(0.3)

    print(f"\nCorpus at {CORPUS}")


if __name__ == "__main__":
    main()
