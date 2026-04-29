# Phase 3 总览（智能体应用栈）

> 本文档汇总 Phase 3 全部 5 个子阶段的交付内容，作为面试时给面试官看的"项目门面"。

## 整体架构

```
┌──────────────────────────────────────────────────────────┐
│   前端：Vue 2 + ElementUI + ECharts                       │
│   /ai (慧聚答疑) → 单轮聊天 → LoRA Qwen3-1.7B 本地推理      │
│   /agent (智能助手) → 多轮 Agent + RAG → DeepSeek 云端     │
└────────────────────────┬─────────────────────────────────┘
                         │ HTTP / SSE
                         ▼
┌──────────────────────────────────────────────────────────┐
│   后端 Flask                                              │
│   ┌─────────────────────────────────────────────────────┐ │
│   │  Plan → Execute → Synthesize → Reflect → END         │ │
│   │  (LangGraph 状态机 + 反思纠错闭环)                    │ │
│   └────┬────────────────┬──────────────┬─────────────────┘ │
│        │                │              │                   │
│   ┌────▼─────┐     ┌────▼─────┐  ┌─────▼─────────────┐     │
│   │ 5 Tools   │     │ RAG       │  │ Reflector LLM     │     │
│   │ (rate/    │     │ bge-m3 +  │  │ (score 1-10,     │     │
│   │  predict/ │     │ reranker +│  │  retry if <7)     │     │
│   │  VaR/...) │     │ ChromaDB  │  └───────────────────┘     │
│   └───────────┘     └───────────┘                            │
│        │                │                                    │
│   ┌────▼─────┐     ┌────▼─────────────┐                     │
│   │ MySQL     │     │ 30 docs 策展语料 │                     │
│   │ 真实汇率  │     │ 央行/概念/风险  │                     │
│   └───────────┘     └───────────────────┘                   │
└──────────────────────────────────────────────────────────┘
                         │
                         ▼
┌──────────────────────────────────────────────────────────┐
│   可观测性：Langfuse （trace plan/tool/latency/token）     │
└──────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────┐
│   并行入口：MCP Server（FastMCP）                         │
│   Cursor / Claude Desktop 等 MCP 客户端通过 stdio 直接调用 │
│   → 共享同一组工具实现，不重复维护                        │
└──────────────────────────────────────────────────────────┘
```

## 5 个子阶段一览

| 阶段 | 交付 | 关键模块 |
|---|---|---|
| **3.1** RAG 检索栈 | bge-m3 dense + bge-reranker-v2-m3 重排 + ChromaDB 持久化向量库 | `app/rag/` |
| **3.2** Agent 集成 | 5 个 Function Calling 工具 + 三层提示词防御 + Langfuse trace 埋点 | `app/agent/tools.py` `app/agent/core.py` |
| **3.3** MCP Server | FastMCP 包装 5 工具 + 1 resource，stdio + HTTP 双协议 | `mcp_server/server.py` |
| **3.4** Langfuse 观测 | 每次 Agent 调用生成 trace，含 plan / tool / latency / token；优雅降级 | `app/observability.py` |
| **3.5** LangGraph + Reflector | StateGraph 状态机（双轨）+ 反思纠错闭环 + 自动重试 | `app/agent/graph.py` `app/agent/core.py` |

## JD 要求覆盖矩阵（蚂蚁智能体与大模型应用工程）

| JD 条目 | 子阶段 | 实现位置 |
|---|---|---|
| **必备**：Prompt Engineering | 3.2 | system prompt 三层防御反例 |
| **必备**：Context Engineering | 3.1, 3.2 | RAG metadata 过滤 + tool description 反例 |
| **必备**：Function Calling | 3.2 | OpenAI tools API 5 工具 + 多轮循环 |
| **必备**：Agent 框架（LangChain 等） | 3.5 | LangGraph StateGraph |
| **必备**：意图识别 + 任务拆解 | 3.5 | Planner 节点 + 路由函数 |
| **必备**：反思纠错闭环 | 3.5 | Reflector 节点 + retry edge |
| **必备**：工具编排 / SDK 封装 | 3.2, 3.3 | tools.py HANDLERS + MCP 协议层 |
| **必备**：自动评测 / 回测 | 3.2, 3.5 | tests/test_agent.py 10 用例 + Reflector 实时评分 |
| **必备**：Agent 观测体系 | 3.4 | Langfuse 全链路 trace |
| **必备**：性能优化 / 异步 / 降级 | 3.1, 3.2, 3.4, 3.5 | RAG warmup, MAX_TOOL_ROUNDS, Reflector graceful no-op, Reranker 降级到 CPU |
| **加分①**：RAG / 多 Agent / **MCP** / Skill | 3.1, 3.3, 3.5 | 全部覆盖 |
| **加分②**：开源 / GitHub | 待发布 | (next phase) |
| **加分③**：vLLM / Ollama / KV cache | 2 | LoRA 走 FastAPI OpenAI 兼容（vLLM 协议同源） |
| **加分④**：SFT / RL 经验 | 2 | Qwen3-1.7B QLoRA + 200 条自合成中文 Q&A |
| **加分⑤**：幻觉 / Prompt 注入应对 | 3.5 | Reflector 4 类典型 bad case 检测 |

## 演示路径（10 分钟版）

### 第一段（2 min）：项目背景 + 架构图
打开本文档，过一遍架构图。强调"已有外汇 Web 应用 → 升级为多 Agent 智能体 + 多协议入口"。

### 第二段（3 min）：Live Agent demo
浏览器 http://localhost:8081/agent，问 3 类问题：
1. **数值类**："美元兑日元的最新汇率？" → trace 显示 `get_exchange_rate` → 真实数字
2. **概念类**："什么是 carry trade？" → trace 显示 `search_forex_knowledge` → citation cards
3. **风险计算**："我有 100 万美元的美元/日元敞口，1 天 99% VaR 是多少？" → trace 显示 `calculate_var` → 含解释

每次都能看到 **🔍 质量审查** 卡片显示 score（多数 8-10）。

### 第三段（2 min）：MCP demo
切到 Claude Desktop（已配置 compass-fx MCP server），同样问"美元兑日元"——Claude Desktop 调用 `compass-fx.get_exchange_rate` 返回相同数据。

> **同一份工具代码，两条入口（Web Agent + MCP）**——这是分层架构的体现。

### 第四段（2 min）：架构亮点
1. 双 LLM 异构路由：/ai → 本地 LoRA（隐私场景），/agent → 云端 DeepSeek（强 tool calling）
2. RAG 检索栈：dense + rerank + metadata filter
3. Reflector：4 类 bad case 自动捕捉 + 智能重试

### 第五段（1 min）：Roadmap
讲下一步 FastAPI 异步、vLLM KV cache、100 题评测集。

## 文件清单（Phase 3 全部）

```
backend/
├── app/
│   ├── agent/
│   │   ├── tools.py             # 5 个工具的实现 + JSON schema
│   │   ├── core.py              # 生产 Agent（Plan/Execute/Synthesize/Reflect linear）
│   │   └── graph.py             # LangGraph StateGraph 版本（portfolio）
│   ├── rag/
│   │   ├── config.py            # 路径 + 检索超参
│   │   ├── embedder.py          # bge-m3 wrapper（CPU 默认）
│   │   ├── reranker.py          # bge-reranker-v2-m3 wrapper（GPU 默认）
│   │   ├── store.py             # ChromaDB 持久化
│   │   ├── ingest.py            # markdown → chunk → embed → store
│   │   └── pipeline.py          # query → dense → rerank → top-k
│   ├── observability.py         # Langfuse 包装 + 优雅降级
│   ├── routes_agent.py          # /api/agent SSE endpoint
│   └── ...
├── mcp_server/
│   ├── server.py                # FastMCP，5 tools + 1 resource
│   ├── README.md                # 接入文档
│   └── claude_desktop_config.example.json
├── data/rag/
│   ├── corpus/                  # 30 篇策展 markdown
│   └── chroma/                  # 持久化向量库
├── scripts/
│   ├── synthesize_corpus.py     # DeepSeek 自合成 corpus
│   └── rebuild_rag.py           # 一键 ingest + smoke
└── tests/
    ├── test_agent.py            # 10 个回归测试
    └── test_mcp_server.py       # MCP stdio smoke

frontend/
└── src/views/Agent.vue          # 工具调用 + RAG citation + reflection 可视化

docs/
├── Phase2_工程笔记.md
├── Phase2_完成报告.md
├── Phase3_RAG.md
├── Phase3_3_MCP.md
├── Phase3_4_Langfuse.md
├── Phase3_5_LangGraph.md
└── Phase3_总览.md (本文档)
```

## 数据点速查（面试 Q&A 储备）

- **LoRA 训练**：Qwen3-1.7B + r=16 + α=32 + bs=2 / ga=8 / no-grad-ckpt / bf16，4060 8GB 单卡 ~20 min（早停 epoch 1，eval loss 4.85→1.30）
- **数据集**：finance-alpaca 抽 3000 + DeepSeek 自合成 200 条中文 Q&A
- **RAG 语料**：30 篇 × 平均 700 字 → 251 chunks（header 切块 + 600 char + 80 overlap）
- **检索流水**：dense top-10（bge-m3 1024 dim）→ reranker 重排 → top-4，端到端 < 2s
- **Agent 工具**：5 个，覆盖数据查询（SQL）、预测（占位）、风险计算（参数法 VaR）、知识检索（RAG）
- **MCP 接入**：stdio 协议（Claude Desktop / Cursor）+ HTTP 协议（远程）
- **Reflector**：score 1-10，threshold=7，max_retries=1，4 类 bad case 模板
