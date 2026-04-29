"""Synthesize Chinese forex SFT data using DeepSeek as the labeling model.

Generates (question, answer) pairs that look like a forex analyst answering a
client. Output is appended to llm/data/zh_synth.jsonl (idempotent — re-runs
extend the file rather than overwriting). Cost on DeepSeek-Chat: ~¥0.5 per 200
examples.

Usage:
    python scripts/synthesize_zh_sft.py            # default 200 pairs
    python scripts/synthesize_zh_sft.py 500        # custom count
"""
from __future__ import annotations

import json
import os
import random
import sys
import time
from pathlib import Path

import requests
from openai import OpenAI

# read backend/.env to get DEEPSEEK key
ROOT = Path(__file__).resolve().parent.parent  # llm/
PROJECT = ROOT.parent  # compass-fx-pulse/
ENV_FILE = PROJECT / "backend" / ".env"
OUT_FILE = ROOT / "data" / "zh_synth.jsonl"


def _load_env() -> dict:
    env = {}
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip()
    return env


# 50 forex topic seeds covering the 6 currencies in our DB
SEEDS = [
    # USD-centric
    "美联储下次议息会议可能的政策路径", "美元指数与新兴市场货币的负相关",
    "美国非农数据对美元的影响机制", "美债收益率倒挂对美元的含义",
    # JPY-centric
    "日本央行 YCC 政策对日元的影响", "日元 carry trade 的逻辑与风险",
    "日本财务省口头干预与实际干预的区别", "日元避险属性的失效条件",
    # EUR-centric
    "ECB 量化紧缩对欧元的影响", "欧元区核心通胀与外围通胀分化",
    "希腊主权债务危机对欧元的长期影响", "欧元兑美元的购买力平价水平",
    # GBP-centric
    "英国央行加息节奏与英镑走势", "英国脱欧对英镑长期走弱的影响",
    "英国通胀粘性对英镑的支撑", "英镑兑欧元的历史均值回归",
    # AUD-centric
    "澳元与铁矿石价格的相关性", "澳洲联储利率决议对澳元的影响",
    "中国制造业 PMI 对澳元的传导机制", "澳元作为大宗商品货币的特征",
    # HKD-centric
    "港币联系汇率制度的运作机制", "金管局保卫港币联系汇率的工具",
    "港股资金流入流出对港币流动性的影响", "港币利率与美联储利率的同步性",
    # 通用主题
    "如何用远期外汇合约做汇率对冲", "VaR 模型在外汇风险计量中的应用",
    "外汇期权与远期合约的对比", "蒙特卡洛模拟在汇率风险中的应用",
    "covered interest parity 失效的条件", "uncovered interest parity 与利差交易",
    "外汇风险的三个层次：交易、折算、经济", "Black-Scholes 在外汇期权定价中的应用",
    "汇率波动率的 GARCH 建模", "外汇市场的微观结构与流动性",
    "央行外汇储备多元化趋势", "SDR 篮子的构成与权重调整",
    "数字人民币对跨境结算的影响", "比特币对法定货币体系的挑战",
    "外汇 swap 的会计处理", "结构性外汇产品的风险拆解",
    # 实战场景
    "出口企业如何用远期锁汇", "进口企业如何用期权降低对冲成本",
    "跨国公司外币应收账款的管理策略", "海外投资的汇率风险敞口度量",
    "个人投资者配置美元资产的时机选择", "QDII 基金的汇率风险传导",
    "外汇局对企业跨境融资的宏观审慎管理", "CFETS 人民币汇率指数的构成",
    "离岸人民币 CNH 与在岸人民币 CNY 的价差含义", "人民币国际化的三个阶段与挑战",
]


PROMPT_TEMPLATE = """你扮演一位资深外汇分析师，根据下面的话题生成一个客户提问和你的专业回答。

话题：{topic}

要求：
1. 问题口语化，模拟客户/企业 CFO 的真实问法（30-60 字）
2. 回答专业、有逻辑、引用机制原理（200-400 字）
3. 不要编造具体当下数值（"截至 X 月美元/日元报 Y"），可用历史区间或定性描述
4. 如适合，分点回答

严格按以下 JSON 格式输出，不要任何额外文字：
{{
  "question": "...",
  "answer": "..."
}}"""


def _generate_one(client: OpenAI, model: str, topic: str) -> dict | None:
    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "你是一位严谨的外汇分析师，输出严格遵循 JSON 格式。"},
                {"role": "user", "content": PROMPT_TEMPLATE.format(topic=topic)},
            ],
            temperature=0.7,
            max_tokens=1000,
            response_format={"type": "json_object"},
        )
        text = resp.choices[0].message.content
        obj = json.loads(text)
        if "question" in obj and "answer" in obj:
            obj["topic"] = topic
            return obj
    except Exception as exc:
        print(f"  [!] {topic[:30]}... → {exc}")
    return None


def _existing_count() -> int:
    if not OUT_FILE.exists():
        return 0
    return sum(1 for _ in OUT_FILE.open("r", encoding="utf-8"))


def main() -> None:
    target = int(sys.argv[1]) if len(sys.argv) > 1 else 200

    env = _load_env()
    api_key = env.get("LLM_API_KEY") or os.getenv("LLM_API_KEY")
    base_url = env.get("LLM_BASE_URL", "https://api.deepseek.com/v1")
    model = env.get("LLM_MODEL", "deepseek-chat")
    if not api_key or api_key == "please_fill_in":
        print("ERROR: LLM_API_KEY not set in backend/.env")
        sys.exit(1)

    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    existing = _existing_count()
    need = max(0, target - existing)
    print(f"Existing: {existing} | target: {target} | to generate: {need}")
    if need == 0:
        return

    client = OpenAI(api_key=api_key, base_url=base_url)
    rng = random.Random(42 + existing)

    written = 0
    with OUT_FILE.open("a", encoding="utf-8") as f:
        for i in range(need):
            topic = rng.choice(SEEDS)
            # add a small variation hint
            variation = rng.choice([
                "（场景：跨国企业 CFO 询问）",
                "（场景：个人投资者）",
                "（场景：外汇交易员）",
                "（场景：财经记者）",
                "（角度：从机制原理出发）",
                "（角度：从历史案例出发）",
            ])
            full_topic = f"{topic} {variation}"

            obj = _generate_one(client, model, full_topic)
            if obj:
                f.write(json.dumps(obj, ensure_ascii=False) + "\n")
                f.flush()
                written += 1
                print(f"  [{written}/{need}] {topic[:30]}... ({len(obj['answer'])} chars)")
            time.sleep(0.3)  # gentle rate limiting

    print(f"\nDone. Wrote {written} new examples → {OUT_FILE}")


if __name__ == "__main__":
    main()
