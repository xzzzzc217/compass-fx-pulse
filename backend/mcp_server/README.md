# CompassFX MCP Server

把 Function Calling Agent 的 5 个工具用 [Model Context Protocol](https://modelcontextprotocol.io/)
重新暴露一遍。任何 MCP 客户端（Claude Desktop / Cursor / Cline / Continue / your own SDK）
都能直接调用，不需要走 Flask Agent。

## 工具清单

| 名字 | 作用 | 复用了 | 
|---|---|---|
| `get_exchange_rate` | 单点汇率查询 | `app.agent.tools._get_exchange_rate` |
| `get_rate_range` | 范围统计（min/max/mean/stdev） | `app.agent.tools._get_rate_range` |
| `predict_exchange_rate` | 30 天预测 | `app.agent.tools._predict_rate` |
| `calculate_var` | 参数法 VaR | `app.agent.tools._calculate_var` |
| `search_forex_knowledge` | RAG（bge-m3 + bge-reranker） | `app.agent.tools._search_knowledge` |

外加一个 resource：
- `compass-fx://corpus/{filename}` — 直接读 corpus markdown 文档

## 快速测试（不需要任何 MCP 客户端）

```powershell
conda activate compass-fx
cd D:\花旗杯\compass-fx-pulse\backend
python tests/test_mcp_server.py
```

输出应包含：
```
PASS — all 5 expected tools present
PASS  (get_exchange_rate)
PASS  (get_rate_range)
PASS  (search_forex_knowledge)
ALL SMOKE TESTS DONE
```

## 接入 Claude Desktop

### 1. 找到 config 文件

Windows: `%APPDATA%\Claude\claude_desktop_config.json`

如果不存在就创建。

### 2. 加 MCP server 配置

```json
{
  "mcpServers": {
    "compass-fx": {
      "command": "C:\\Users\\21398\\Miniconda3\\envs\\compass-fx\\python.exe",
      "args": ["-m", "mcp_server.server"],
      "cwd": "D:\\花旗杯\\compass-fx-pulse\\backend",
      "env": {
        "PYTHONUTF8": "1",
        "KMP_DUPLICATE_LIB_OK": "TRUE",
        "OMP_NUM_THREADS": "1"
      }
    }
  }
}
```

> **替换路径**：`command` 改成你的 conda env Python；`cwd` 改成你的 backend 路径。

### 3. 重启 Claude Desktop

启动后右下角应看到 🔨 锤子图标，点开能列出 5 个 compass-fx 工具。

### 4. 实测

新对话里说："帮我查一下美元兑日元的最新汇率"——Claude 应该自动调用 `compass-fx.get_exchange_rate`。

## 接入 Cursor

`.cursor/mcp.json` 在你的项目根目录（不是 CompassFX，是你想让 Cursor 用 MCP 的那个项目）：

```json
{
  "mcpServers": {
    "compass-fx": {
      "command": "C:\\Users\\21398\\Miniconda3\\envs\\compass-fx\\python.exe",
      "args": ["-m", "mcp_server.server"],
      "cwd": "D:\\花旗杯\\compass-fx-pulse\\backend",
      "env": {
        "PYTHONUTF8": "1",
        "KMP_DUPLICATE_LIB_OK": "TRUE"
      }
    }
  }
}
```

Cursor 会自动检测，在 Composer 里能直接调用工具。

## 接入 Cline / Continue / 自定义客户端

任何支持 MCP 的客户端配置都是同样的结构（command + args + env）。

## HTTP / SSE 模式（远程集成）

如果想跨机器调用（比如 Claude Code 在另一台机），用 HTTP transport：

```powershell
python -m mcp_server.server --http 9001
```

然后客户端用 `Streamable HTTP` 接入 `http://127.0.0.1:9001/mcp`。

## 架构（面试讲法）

```
┌──────────────────────────────────┐
│ Cursor / Claude Desktop / 客户端  │
└──────────────┬───────────────────┘
               │ MCP（JSON-RPC over stdio）
               ▼
┌──────────────────────────────────┐
│  mcp_server/server.py             │
│  FastMCP，7 个工具/resource         │
└──────────────┬───────────────────┘
               │ Python import (零网络开销)
               ▼
┌──────────────────────────────────┐
│  app/agent/tools.py               │  ← 复用 Flask Agent 同一份实现
│  app/rag/pipeline.py              │
│  app/db.py                        │
└──────────────────────────────────┘
```

> **关键设计**：MCP server 和 Flask backend **共享 tools.py**，单一来源。
> 改一个工具，两个入口（HTTP API + MCP）同时受益。**避免代码重复**是工程纪律。

## 故障排查

| 现象 | 原因 | 修法 |
|---|---|---|
| Claude Desktop 没看到工具 | command 路径错 / cwd 错 | 用绝对路径，重启 Claude Desktop |
| 第一次调用 RAG 卡 30 秒 | bge-m3 + reranker 冷加载 | 正常，第二次起秒级 |
| 调用立刻报 `LLM_API_KEY missing` | MCP 工具不调用 LLM，但导入 tools.py 时拿了 settings | 已经在 tools.py 里 lazy 化，不应再发生 |
| `MySQLConnector: Access denied` | MCP server 进程没继承 .env | 在 mcp config 的 env 里手动加 MYSQL_PASSWORD |
