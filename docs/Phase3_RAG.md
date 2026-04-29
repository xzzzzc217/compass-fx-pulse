# Phase 3.1 + 3.2 — RAG 知识库 + Agent 集成

> Phase 3 第一段：让 Agent 不再只会"查数据库"，还能"查知识库"，从而专业回答概念/政策/机制类问题。

## 架构

```
用户问"什么是 carry trade"
       │
       ▼
┌──────────────────────────┐
│  Function Calling LLM   │  DeepSeek (router)
│  决策：路 RAG 还是数据 ?  │
└────────┬─────────────────┘
         │ tool_call: search_forex_knowledge(query="carry trade")
         ▼
┌──────────────────────────┐
│  RAG Pipeline           │
│  ┌─────────────────────┐│
│  │ bge-m3 dense embed  ││  query → 1024-dim vector
│  └─────────────────────┘│
│  ┌─────────────────────┐│
│  │ Chroma top-20       ││  cosine similarity
│  └─────────────────────┘│
│  ┌─────────────────────┐│
│  │ bge-reranker-v2-m3  ││  rescore + cut to top-5
│  └─────────────────────┘│
└────────┬─────────────────┘
         │ JSON list of {title, text, score, source}
         ▼
┌──────────────────────────┐
│  LLM 综合 + 引用      │
│  "根据 [来源 1]: ..."   │
└──────────────────────────┘
```

## 技术选型

| 决策 | 选择 | 理由 |
|---|---|---|
| 嵌入模型 | **bge-m3** (~2.27GB) | BAAI 的金标，CN+EN 多语种，支持 dense + sparse + ColBERT 三种向量 |
| 重排模型 | **bge-reranker-v2-m3** (~568MB) | 配套 m3，跨编码器，CN+EN 双语 |
| 向量库 | **ChromaDB** (本地 SQLite + DuckDB) | 零基础设施（无 Docker），单 pip install，PersistentClient 落盘 |
| 切块策略 | **header-bounded** + 600-char hard limit + 80-char overlap | 保留 markdown 语义结构 |
| 检索流程 | dense top-20 → rerank → top-5 + min_score 阈值 | hybrid retrieval 经验配置 |
| 元数据 | category / currency / source_file | 支持 metadata 过滤（如 `currency=JPY`） |

## 语料

30 篇 markdown 文档，覆盖 4 大类：

| 类别 | 数量 | 内容 |
|---|---|---|
| `currency` | 6 | 6 大币种的国际地位、历史、特性 |
| `concept` | 12 | carry trade、CIP、UIP、VaR、GARCH、PPP、IV smile、swap points、yield curve、BOP、intervention、microstructure |
| `risk` | 6 | 企业对冲、远期定价、期权策略、自然对冲、VaR 限额、折算风险 |
| `policy` | 6 | Fed FOMC、ECB、BOJ YCC、PBOC CFETS、HKMA 联系汇率、RBA |

每篇 500-900 字，包含定义/机制/工具/案例。**用 DeepSeek 自合成**——10 分钟 / ¥1，可重复执行。

## RAG 模块文件清单

```
backend/
├── app/
│   └── rag/
│       ├── config.py        # 路径、模型路径、超参
│       ├── embedder.py      # bge-m3 wrapper（lazy singleton）
│       ├── reranker.py      # bge-reranker wrapper
│       ├── store.py         # Chroma client + collection
│       ├── ingest.py        # markdown → chunk → embed → store
│       └── pipeline.py      # retrieve(query, k) → ranked chunks
├── data/
│   └── rag/
│       ├── corpus/          # 30 个 markdown
│       └── chroma/          # 持久化向量库
└── scripts/
    ├── synthesize_corpus.py # DeepSeek 生成 corpus
    └── rebuild_rag.py       # 一键 ingest + smoke query
```

## 一键流程

```powershell
conda activate compass-fx
cd D:\花旗杯\compass-fx-pulse\backend

# 1. 生成语料（5 分钟，可跳过——已生成的不重复）
python scripts/synthesize_corpus.py

# 2. 下载 bge 模型（~3GB，5-10 分钟）
cd ..\llm
python scripts/download_rag_models.py
cd ..\backend

# 3. 建索引 + smoke 测试（首次 ~1 分钟）
python scripts/rebuild_rag.py --rebuild --query "什么是 carry trade?"

# 4. 重启后端，Agent 自动看到新工具
python main.py
```

## 在 Agent 里的角色

新增工具：`search_forex_knowledge(query, k=5, currency=?, category=?)`

System prompt 决策路由：
- **数值类**问题（"今天美元兑日元"）→ get_exchange_rate / VaR / predict
- **概念类**问题（"carry trade"、"YCC"、"FOMC"）→ search_forex_knowledge
- **闲聊**：不调用工具

前端 Agent.vue 新增 **Citation Card** 显示——左侧 trace 不再是 raw JSON，而是分段卡片显示 `category / currency / rerank_score / title / 摘要`。

## 评测

新增 7 个测试用例（共 10 个）：
- 应路 RAG：`什么是 VaR` / `FOMC 决策框架` / `carry trade in JPY`
- 应路 数据：rate / range / VaR calc / prediction
- 应**不**调用：闲聊 / 短知识题（"carry trade"）

跑 `python tests/test_agent.py` 应得 9/10 或 10/10。

## 面试讲法（30 秒）

> "Phase 3.1 我把 Agent 从'只能查数据库'升级成'还能查知识库'。架构上：用户提问 → DeepSeek 判定该走 RAG 还是 SQL 工具 → 如果 RAG，bge-m3 做 dense 召回 top-20 → bge-reranker-v2-m3 重排到 top-5 → 注入回 LLM 做答案合成。
>
> 数据上：用 DeepSeek 自合成了 30 篇高质量金融知识文档（6 大币种 / 12 个概念 / 6 个风险管理 / 6 个央行政策），按 markdown header 切块，元数据带 currency 和 category，**支持过滤检索**——比如问'日本央行政策'就能 metadata filter `currency=JPY,category=policy`，召回精度更高。
>
> 工程上选 ChromaDB 不选 Qdrant 是因为零基础设施，PersistentClient 落本地磁盘；模型用 BAAI 的 m3 系列因为 CN+EN 双语场景最稳。前端把 RAG 命中渲染成 citation card，trace 面板能直观看到每个引用的 rerank score——**这是 RAG 调优时最有用的 debug 信号**。"

## 接下来 Phase 3.3-3.5

3.3 **MCP Server**：把 5 个工具（4 数据 + 1 RAG）暴露成 MCP，Cursor / Claude Desktop 直接调用
3.4 **Langfuse 观测**：Trace 每次 Agent 调用的 plan / tool / latency / token usage
3.5 **LangGraph 多 Agent**：拆 Router / Planner / Reflector 状态机，加反思纠错闭环
