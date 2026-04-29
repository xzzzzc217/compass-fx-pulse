# Phase 3.3 — MCP Server

> 把 Function Calling Agent 的 5 个工具用 [Model Context Protocol](https://modelcontextprotocol.io/) 重新暴露，让 Cursor / Claude Desktop / 任何 MCP 客户端能直接调用 CompassFX 的能力。

## 设计

```
┌──────────────────┐  MCP/JSON-RPC stdio  ┌──────────────────────┐
│  Claude Desktop  │ ◄──────────────────► │  mcp_server/server.py │
│  Cursor          │                      │  (FastMCP, lazy init) │
│  自定义 MCP 客户端 │                      └──────────┬───────────┘
└──────────────────┘                                 │ Python import
                                                     ▼
                                       ┌──────────────────────────┐
                                       │  app/agent/tools.py       │ ← 单一来源
                                       │  app/rag/pipeline.py      │
                                       │  app/db.py                │
                                       └──────────────────────────┘
```

**关键设计**：MCP server 与 Flask Agent **共享 `app/agent/tools.py`**。修改任一工具自动同步两边。

## 暴露的能力

| 类型 | 名字 | 复用 |
|---|---|---|
| Tool | `get_exchange_rate` | `_get_exchange_rate` |
| Tool | `get_rate_range` | `_get_rate_range` |
| Tool | `predict_exchange_rate` | `_predict_rate` |
| Tool | `calculate_var` | `_calculate_var` |
| Tool | `search_forex_knowledge` | `_search_knowledge`（含 RAG） |
| Resource | `compass-fx://corpus/{filename}` | 直接读 corpus markdown |

## 测试

```powershell
conda activate compass-fx
cd D:\花旗杯\compass-fx-pulse\backend

# 快速：4 个数据工具（10 秒）
python tests\test_mcp_server.py

# 完整：含 RAG 工具（首次 ~60 秒冷加载）
python tests\test_mcp_server.py --with-rag
```

期望：5 PASS（不带 RAG）或 6 PASS（带）。

## 接入 Claude Desktop（5 分钟）

1. 找到 `%APPDATA%\Claude\claude_desktop_config.json`（不存在就创建）
2. 复制 `backend/mcp_server/claude_desktop_config.example.json` 内容进去（路径替换成你的）
3. 重启 Claude Desktop
4. 右下角 🔨 图标点开应能看到 5 个 compass-fx 工具
5. 对话框试："美元兑日元的汇率是多少？" → Claude 自动调用 `compass-fx.get_exchange_rate`

## 接入 Cursor

`.cursor/mcp.json` 在你的项目根（不是 CompassFX 项目，是任何你想让 Cursor 用 MCP 的项目）：
同样的 JSON 结构。Cursor Composer 自动检测。

## 工程亮点（面试讲法）

> "Phase 3.3 我把 Function Calling Agent 的 5 个工具用 MCP 协议重新暴露了一遍，Claude Desktop / Cursor 现在能直接调用我的工具——不需要打开浏览器走 Flask。
>
> 工程上我做了一个'**复用而不重复**'的决定：MCP server 不重写工具实现，直接 import `app/agent/tools.py` 的 HANDLERS，加一层 FastMCP 装饰器变成 MCP tool。改一处工具，HTTP API + MCP 两个入口同步生效。这是分层架构的体现——Tool 是业务逻辑层，Agent / MCP 是协议层，不应该耦合。
>
> 部署上踩了 Windows-specific 坑：MCP server 是 stdio 子进程，每次 Claude Desktop 启动都新起一个 Python，bge-m3 + reranker 冷加载 30-60 秒。修法是加 `--warmup-rag` 选项让用户决定是否预热（默认 lazy，避免每次 Claude 启动都等）。
>
> 这套实现命中蚂蚁 JD 加分项里写明的'**结合 MCP、Skill 等的 Agent 项目**'。"

## 文件清单

```
backend/
├── mcp_server/
│   ├── __init__.py
│   ├── server.py                              # FastMCP server + 5 tools + 1 resource
│   ├── README.md                              # 安装/接入文档
│   └── claude_desktop_config.example.json     # 一键拷贝模板
└── tests/
    └── test_mcp_server.py                     # stdio 客户端 smoke test
```

## 下一步

Phase 3.4 — Langfuse 全链路 Trace。把 Agent + MCP 的每次调用（plan / tool / latency / token）写到 Langfuse，前端能看到瀑布图。
