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

## 配置原则（先看这里！）

实测踩过两个 Windows 坑，所有 MCP 客户端配置都按下面写就稳：

1. **`command` 必须是 conda env python.exe 的绝对路径**——GUI 应用不继承 shell PATH，写 `python` 会拿到系统默认 Python（多半没装 mcp 包）。
2. **`args[0]` 直接给 `server.py` 的绝对路径，不要用 `-m mcp_server.server`**——后者依赖 `cwd`，而 Claude Desktop 改写 config 时可能把 `cwd` 字段抹掉，加上中文路径解析风险，模块发现就会失败。
3. **设 `PYTHONPATH`** 显式注入 backend/ 到 sys.path——双保险，不依赖 cwd 或 sys.path[0] 推断。
4. **设 `PYTHONIOENCODING=utf-8` + `PYTHONUTF8=1`**——防止 stdio JSON-RPC 在中文 locale 下被 GBK 解码搞炸。

## 接入 Claude Desktop

### 1. 找到 config 文件

Windows: `%APPDATA%\Claude\claude_desktop_config.json`（不存在就创建）。

### 2. 加 MCP server 配置

参照 [`claude_desktop_config.example.json`](claude_desktop_config.example.json)：

```json
{
  "mcpServers": {
    "compass-fx": {
      "command": "C:\\Users\\21398\\Miniconda3\\envs\\compass-fx\\python.exe",
      "args": [
        "D:\\花旗杯\\compass-fx-pulse\\backend\\mcp_server\\server.py"
      ],
      "env": {
        "PYTHONIOENCODING": "utf-8",
        "PYTHONUTF8": "1",
        "PYTHONPATH": "D:\\花旗杯\\compass-fx-pulse\\backend",
        "KMP_DUPLICATE_LIB_OK": "TRUE",
        "OMP_NUM_THREADS": "1"
      }
    }
  }
}
```

> **替换 3 处**：① `command` 改成你的 conda env python.exe；② `args[0]` 改成 `<your-repo>\backend\mcp_server\server.py`；③ `PYTHONPATH` 改成 `<your-repo>\backend`。

### 3. 完全退出 Claude Desktop（任务栏右键 Quit，不只是关窗口）然后重新打开

启动后顶部应看到 🔨 锤子图标，点开能列出 5 个 compass-fx 工具。

### 4. 实测

新对话里说："帮我查一下美元兑日元的最新汇率"——Claude 应该自动调用 `compass-fx.get_exchange_rate`。

## 接入 Cursor

Cursor 支持两种 MCP 配置位置：

### 方式 A · 项目级（推荐）

在**目标项目**根目录（不是 compass-fx-pulse 本身，是你希望用 MCP 的那个项目）创建 `.cursor/mcp.json`：

```json
{
  "mcpServers": {
    "compass-fx": {
      "command": "C:\\Users\\21398\\Miniconda3\\envs\\compass-fx\\python.exe",
      "args": [
        "D:\\花旗杯\\compass-fx-pulse\\backend\\mcp_server\\server.py"
      ],
      "env": {
        "PYTHONIOENCODING": "utf-8",
        "PYTHONUTF8": "1",
        "PYTHONPATH": "D:\\花旗杯\\compass-fx-pulse\\backend",
        "KMP_DUPLICATE_LIB_OK": "TRUE",
        "OMP_NUM_THREADS": "1"
      }
    }
  }
}
```

模板见 [`cursor_mcp.example.json`](cursor_mcp.example.json)。

### 方式 B · 用户级（全局生效）

`%USERPROFILE%\.cursor\mcp.json`（即 `C:\Users\<your-user>\.cursor\mcp.json`），格式同上。

### 验证步骤

1. **重启 Cursor**（File → Quit 完整退出）
2. 打开 **Cursor Settings → MCP**（Ctrl+Shift+J → 选 MCP 标签 / 或 `Cmd/Ctrl+,` 搜 mcp）
3. 应该看到 `compass-fx` server，状态绿色，列出 5 个工具
4. 在 Composer / Chat 里输入 `@compass-fx`，自动补全工具名，或自然语言提问 "美元兑日元最新汇率多少？" → Cursor 自动调用 `get_exchange_rate`
5. 工具调用前 Cursor 会弹"是否允许 compass-fx 调 X"对话框 — 确认即可

### Composer 里直接调

Cursor Agent 模式（Cmd+I）下输入：

```
帮我用 compass-fx 工具查一下：
1. 美元兑日元最新汇率
2. 100 万美元兑日元头寸的 1 天 99% VaR
3. 解释一下 carry trade 是什么
```

Cursor 应该串联 3 次调用，分别对应 `get_exchange_rate` / `calculate_var` / `search_forex_knowledge`。

## 接入 Cline / Continue / 自定义客户端

任何支持 MCP 的客户端都是同一份配置结构（`command` + `args` + `env`）。如果文档要求 `cwd` 字段，照填即可（用绝对路径），但**不要依赖它**——按上面的"配置原则"加 PYTHONPATH 是最稳的。

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
| Claude Desktop / Cursor 没看到工具 | command 是 `python` 不是绝对路径 → 拿到系统 Python（无依赖） | command 写 conda env python.exe 绝对路径 |
| 日志报 `ModuleNotFoundError: No module named 'mcp_server'` | 用 `-m mcp_server.server` + `cwd`，但客户端把 cwd 抹掉了 | 改成直接给 server.py 绝对路径 + 设 `PYTHONPATH` |
| `Could not attach to MCP server` / `Server disconnected` | 子进程启动后立刻退出（多半 ImportError） | 看 `%APPDATA%\Claude\logs\mcp-server-<name>.log` 找根因 |
| 第一次调用 RAG 60 秒超时 | bge-m3 (2.27GB) + reranker (568MB) 冷加载，超过默认 60s timeout | 正常，第二次起秒级；面试前先在浏览器调一次预热 |
| 调用立刻报 `LLM_API_KEY missing` | MCP 工具本身不调 LLM，但 tools.py 导入时读了 settings | 已经 lazy 化，若复现请提 issue |
| `MySQLConnector: Access denied` | MCP server 子进程没读到 .env | 在 mcp config 的 `env` 里手动加 `MYSQL_PASSWORD` |
| 中文路径下 stdio 协议解码报错 | Windows GBK 默认 locale | 在 `env` 里加 `PYTHONIOENCODING=utf-8` + `PYTHONUTF8=1` |
