# Backend

Flask + MySQL + DeepSeek。模块化布局，每个 blueprint 一个文件。

## 目录

```
backend/
├── main.py                  # 入口，注册 blueprint
├── app/
│   ├── config.py            # 从 .env 读取配置
│   ├── db.py                # MySQL 连接池 + 上下文管理
│   ├── llm.py               # OpenAI 兼容客户端，支持 SSE 流式
│   ├── routes_chat.py       # /api/messages, /api/count, /api/multiple-messages
│   ├── routes_rates.py      # /api/exchange_rates, /api/exchange_rate_prediction
│   └── routes_health.py     # /api/health
├── scripts/
│   ├── init_db.sql          # 库 + 表 + 索引（幂等）
│   ├── backfill_rates.py    # yfinance 回填真实汇率
│   └── seed_predictions.py  # 占位预测，Phase 2 由 TimeXer 替换
├── tests/                   # （留空，Phase 1 加 pytest）
├── requirements.txt
├── .env.example
└── .gitignore
```

## 运行

```bash
conda activate compass-fx
cp .env.example .env  # 然后编辑
python main.py
```

## API

| Method | Path | 描述 |
|---|---|---|
| GET | `/api/health` | 探活，返回 DB / LLM 状态 |
| GET | `/api/exchange_rates?currencyA=&currencyB=&start_date=&end_date=` | 历史汇率范围查询 |
| GET | `/api/exchange_rate_prediction?currencyA=&currencyB=` | 预测序列 |
| GET | `/api/messages?query=...` | SSE 流式问答 |
| POST | `/api/count` | 保存一轮对话到 `aichat` 表 |
| GET | `/api/multiple-messages` | 加载历史对话 |

## 添加新工具 / 路由（Phase 2 起）

```python
# app/routes_tools.py
from flask import Blueprint, jsonify
bp = Blueprint("tools", __name__)

@bp.get("/api/tools/risk")
def calc_risk():
    ...
    return jsonify(...)

# main.py
from app.routes_tools import bp as tools_bp
app.register_blueprint(tools_bp)
```

## 切换 LLM

只改 `.env` 的 `LLM_BASE_URL` / `LLM_MODEL` / `LLM_API_KEY`，重启后端即可。
代码层面（`app/llm.py`）走 OpenAI SDK，所有 OpenAI-兼容服务（DeepSeek、阿里云百炼、Ollama、OpenAI、SiliconFlow、Together）通用。
