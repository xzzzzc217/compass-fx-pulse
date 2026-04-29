# Phase 3.5 — LangGraph 多 Agent + Reflector

> 把"单 Agent + 工具循环"升级成显式的 **Plan → Execute → Synthesize → Reflect → (retry/end)** 状态机。
> JD 对应：「意图识别、任务拆解与反思纠错闭环」+「LangChain 等主流 Agent 框架」

## 双轨交付

考虑到生产稳定性，Phase 3.5 走双轨：

| 路径 | 文件 | 用途 |
|---|---|---|
| **生产** | [`app/agent/core.py`](../backend/app/agent/core.py) | live 服务 `/api/agent`，加了 Reflector 步骤 + 重试，保留 SSE 流式 UX |
| **架构参考** | [`app/agent/graph.py`](../backend/app/agent/graph.py) | LangGraph StateGraph 实现，可视化 + 易扩展，作 portfolio 工件 |

两份代码逻辑一致，调用同一组工具（`app/agent/tools.py`），不会双重维护。

## 状态机

```
                ┌─────────────────────────┐
                │       START             │
                └──────────┬──────────────┘
                           ▼
                ┌─────────────────────────┐
   ┌───────────▶│       planner            │
   │            │  LLM 决策：调工具？答？  │
   │            └─────┬───────────┬────────┘
   │                  │ tool_calls │ no tools
   │                  ▼           ▼
   │         ┌──────────────┐  (skip exec)
   │         │   executor   │      │
   │         │  跑所有工具  │      │
   │         └──────┬───────┘      │
   │ MAX 2 rounds   │              │
   └────────────────┤              ▼
                    └─────────▶ ┌─────────────────┐
                                │  synthesizer     │
                                │  生成草稿        │
                                └────────┬─────────┘
                                         ▼
                                ┌─────────────────┐
              retry (score<7)   │   reflector      │
              ┌─────────────────│  审查 score 1-10 │
              │                 └────────┬─────────┘
              │                          │ score>=7
              │                          ▼
              │                 ┌─────────────────┐
              └────────────────▶│   finalize       │
                                │  返回 final     │
                                └────────┬─────────┘
                                         ▼
                                       END
```

## Reflector 设计

输入：`(用户问题, 工具结果摘要, 草稿回答)`
输出（严格 JSON）：
```json
{ "score": 1-10, "issues": "...", "suggestion": "..." }
```

评分维度（System Prompt 里硬编码）：
1. 涉及具体数值时是否使用了 tool 返回的真实数字（防幻觉）
2. 概念/政策类问题是否引用了 RAG 知识库
3. 是否编造 tool_results 中不存在的数据
4. 是否答非所问

**`score >= 7`** → 通过，进 finalize
**`score < 7`** 且 `retry_count < 1` → 回 synthesizer，**带上 reflector 的 issues + suggestion 作为额外 system prompt**
**`score < 7`** 且 `retry_count >= 1` → 直接 finalize（避免无限循环）

## UX 取舍

加 Reflector 后，原本可以"边生成边流式"的合成步改成了"先收满草稿再审查"。

| 维度 | Before | After |
|---|---|---|
| 首字延迟 | 立刻开始流（用户立刻看到响应） | 等草稿+审查完才开始流（多 ~3-5 秒） |
| 答案质量 | 无质量门 | **过质量门后才发**（无半流式发现错的情况） |
| 失败处理 | 只能回滚一整段 | Reflector 引导针对性重写 |

为保留流式视觉效果，最终发的不是 LLM 流，而是 `_chunk_text(draft, chunk_size=4)` ——把审过的整段按 4 字一节往前端推，**视觉上仍是逐字打字效果**。

## 前端可视化

`Agent.vue` 的 trace 面板新增 **🔍 质量审查** 卡片：
- 通过：绿色 score pill `7/10`
- 不通过：红色 score pill `5/10` + issues + suggestion + `↻ 触发重新合成` 提示

实战中能直接看到 Agent 的"自检"过程——这是面试 demo 的核心差异化。

## 故障兜底

- Reflector LLM 调用失败 / JSON 解析失败 / 超时 → 默认 `score=10`（pass-through），**不阻塞用户拿到答案**
- `MAX_REFLECTION_RETRIES = 1`（上限 1 次重试），保证最坏延迟可预测
- 整个 reflection 模块**异常被吞**到 `_reflector_error` 字段，仅落到 Langfuse trace，不向用户暴露

## 跑一下

CLI 单 query 测试：
```powershell
conda activate compass-fx
cd D:\花旗杯\compass-fx-pulse\backend
python -m app.agent.graph "美元兑日元的最新汇率是多少？"
```

输出 mermaid 图：
```powershell
python -m app.agent.graph --print-graph
```

得到的 mermaid 可粘到 https://mermaid.live 直接渲染成图，简历 / 文档可贴。

## 面试讲法

> "Phase 3.5 我把 Agent 升级成 LangGraph 状态机：Plan → Execute → Synthesize → Reflect → (retry/end)。
>
> 关键加的是 **Reflector 节点**——一个 LLM 评审员，给草稿打 1-10 分。低于 7 触发回 Synthesizer 重生成，并把审查意见作为 system prompt 注入指导。
>
> 这套设计直接对应 JD 里写的'**意图识别、任务拆解与反思纠错闭环**'。Reflector 抓住了 4 类典型 bad case：
> ① LLM 编造工具未返回的数据
> ② 概念问题没引用 RAG 召回的段落
> ③ 答非所问
> ④ 数值计算复述错误
>
> 工程上**双轨实现**：生产 `core.py` 走线性 Python 流式（首字延迟 3-5s 但视觉仍流畅），portfolio `graph.py` 用 LangGraph 显式状态机（架构清晰、可视化、可导出 mermaid）。两边共享同一组工具实现，不重复维护。"

## 接下来（可选 / Phase 4 起点）

- 把 Reflector 拆成多专家投票（Critic Ensemble）
- 引入 LangGraph 的 **interrupt / human-in-the-loop**：低 score 时暂停等用户决定
- 接 LangSmith 评测套件，跑评测集对比 retry on/off 的质量提升
