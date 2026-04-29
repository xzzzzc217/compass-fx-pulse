"""Quick token-rate benchmark for the local LoRA serve.

Usage:
    python bench_serve.py
"""
import time

import requests

PROMPT = "用中文写一段 100 字关于外汇风险的介绍"
URL = "http://127.0.0.1:8001/v1/chat/completions"


def main() -> None:
    t0 = time.time()
    r = requests.post(
        URL,
        json={
            "model": "qwen3-1.7b-finance",
            "messages": [{"role": "user", "content": PROMPT}],
            "max_tokens": 150,
            "temperature": 0.7,
            "stream": False,
        },
        timeout=120,
    )
    elapsed = time.time() - t0
    d = r.json()
    ntok = d["usage"]["completion_tokens"]
    print(f"{ntok} tokens in {elapsed:.2f}s = {ntok / elapsed:.1f} tok/s")
    print("answer:", d["choices"][0]["message"]["content"][:300])


if __name__ == "__main__":
    main()
