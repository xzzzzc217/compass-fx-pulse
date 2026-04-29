# CompassFXPulse

外汇行情、走势预测与智能问答的端到端 Web 应用。

```
frontend/  Vue 2 + ElementUI + ECharts (webpack 3)
backend/   Flask + MySQL + DeepSeek (OpenAI 兼容)，模块化布局
llm/       LoRA 微调脚本（Phase 2）
infra/     docker-compose、部署脚本（Phase 1）
docs/      架构、维护与升级方案
```

## 快速启动（约 10 分钟，假设 MySQL 已装）

### 1. Python 环境
```bash
conda create -n compass-fx python=3.12 -y
conda activate compass-fx
cd backend
pip install -r requirements.txt
```

### 2. 配置 `.env`
```bash
cd backend
cp .env.example .env
# 编辑 .env，至少填：
#   MYSQL_PASSWORD = 你的 MySQL root 密码
#   LLM_API_KEY    = 在 https://platform.deepseek.com/ 申请
```

### 3. 初始化数据库
```bash
mysql -u root -p < scripts/init_db.sql
python scripts/backfill_rates.py        # 拉 2024-01-01 到今天的真实汇率
python scripts/seed_predictions.py      # 占位预测，让"汇率预测"页能渲染
```

### 4. 启动后端
```bash
python main.py
# 浏览器打开 http://127.0.0.1:8080/api/health 应返回 {"status":"ok",...}
```

### 5. 启动前端
```bash
# 由于 Webpack 3 与新 Node 不兼容：
nvm use 16   # 或：set NODE_OPTIONS=--openssl-legacy-provider
cd frontend
npm install
npm run dev
# 浏览器自动打开 http://localhost:8080（webpack-dev-server 默认端口）
```

> ⚠️ 前端 webpack-dev-server 默认也用 8080，与后端冲突。
> 临时方案：`PORT=8081 npm run dev`，或在后端 `.env` 把 `PORT` 改成 5000。

## 健康检查

```
GET /api/health
{
  "status": "ok",
  "db":  {"ok": true, "error": null},
  "llm": {"provider": "deepseek", "model": "deepseek-chat", "key_loaded": true}
}
```

任一项 `ok` 为 `false`，对应模块就需要排查。

## 切换 LLM 提供商

只改 `.env`，无需动代码：

| 提供商 | LLM_BASE_URL | LLM_MODEL |
|---|---|---|
| DeepSeek（默认） | `https://api.deepseek.com/v1` | `deepseek-chat` |
| 阿里云百炼（Qwen） | `https://dashscope.aliyuncs.com/compatible-mode/v1` | `qwen-plus` |
| 本地 Ollama | `http://127.0.0.1:11434/v1` | `qwen2.5:7b-instruct` |
| OpenAI | `https://api.openai.com/v1` | `gpt-4o-mini` |

## 路线图

- **Phase 0** ✅ — 修复并接通：数据回填到 2026-04，AI 问答接 DeepSeek，所有配置走 `.env`
- **Phase 2** ✅ — LoRA 微调 Qwen3-1.7B（金融 SFT，QLoRA + 自合成 200 条 Q&A），FastAPI OpenAI 兼容服务，与云端 DeepSeek 经 .env 一行切换。详见 [docs/Phase2_工程笔记.md](docs/Phase2_工程笔记.md)
- **Phase 3.1+3.2** ✅ — Function Calling Agent（5 工具：rate / range / predict / VaR / RAG）+ RAG 检索栈（bge-m3 + bge-reranker + ChromaDB + 30 篇策展语料）。详见 [docs/Phase3_RAG.md](docs/Phase3_RAG.md)
- **Phase 3.3** ✅ — MCP Server（FastMCP），把 5 工具暴露给 Cursor / Claude Desktop。详见 [docs/Phase3_3_MCP.md](docs/Phase3_3_MCP.md)
- **Phase 3.4** ✅ — Langfuse 全链路 Trace（plan / tool / latency / token，graceful no-op）。详见 [docs/Phase3_4_Langfuse.md](docs/Phase3_4_Langfuse.md)
- **Phase 3.5** ✅ — LangGraph 多 Agent 状态机 + Reflector 反思纠错闭环。详见 [docs/Phase3_5_LangGraph.md](docs/Phase3_5_LangGraph.md)
- **Phase 4 (Future)** — Docker compose 一键启动；FastAPI 异步重写；vLLM KV cache 优化；Prompt 注入防护；100 题 LLM-as-Judge 评测集

详见 [docs/维护升级方案.md](docs/维护升级方案.md)。

## 致谢与版权

Phase 0 重构基于 2025 年花旗杯参赛项目源码。原始压缩包保留在仓库外。
原项目设计与开发：花旗杯参赛队（详见 [Notification.txt](docs/Notification.txt)）。
重构、Agent 改造与 LLM 集成：赵子辰。
