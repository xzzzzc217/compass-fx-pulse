# Phase 3.4 — Langfuse Observability

> 给 Function Calling Agent 加全链路 Trace，看见每次调用的：plan / tool / latency / token / cost / 完整对话历史。
> JD 对应：「Agent 观测体系，全链路追踪与多维归因分析」

## 实现

### 优雅降级

`app/observability.py` 是一层薄封装：
- 检测到 `LANGFUSE_PUBLIC_KEY` → 走真实 Langfuse 客户端
- 没设置或失败 → 静默 no-op，**不破任何 user request**

无环境变量时，`obs.enabled == False`，所有 `with obs.trace(...)` 走 dummy 实现，零开销。

### Trace 结构

每个 `/api/agent` 请求 = 一个 `agent_run` trace，里面有：

```
agent_run                            (root span; input=query, output=final answer)
├─ llm_decide_round_1                (generation; model + tokens + cost)
├─ tool:get_exchange_rate            (span; input args + output result)
├─ tool:search_forex_knowledge       (span; ditto)
├─ llm_decide_round_2                (generation; if tools call again)
└─ llm_synthesize                    (generation; the streaming final answer)
```

每个 generation 自动收集：
- model 名
- input messages
- output content
- prompt_tokens / completion_tokens（cost 由 Langfuse 推算）

每个 tool span 收集：
- 调用参数
- 返回结果

### 启用步骤（5 分钟）

1. 注册 free 账号 https://cloud.langfuse.com（每月 100k events 够用）
2. 创建 project → Settings → API Keys → 生成一对
3. `backend/.env` 加：
   ```
   LANGFUSE_PUBLIC_KEY=pk-lf-...
   LANGFUSE_SECRET_KEY=sk-lf-...
   LANGFUSE_HOST=https://cloud.langfuse.com
   ```
4. Ctrl-C 重启 Flask
5. 启动日志应看到：`[obs] Langfuse enabled → https://cloud.langfuse.com`
6. 浏览器 /agent 问几个问题
7. Langfuse 控制台 → Traces 看瀑布图

### 自托管选项

对外暴露要小心隐私的话，可以本地起：
```bash
docker run -p 3000:3000 -e DATABASE_URL=... langfuse/langfuse:latest
```
然后 `LANGFUSE_HOST=http://localhost:3000`，其他配置不变。

## 价值（面试讲法）

> "Phase 3.4 我接了 Langfuse 做 Agent 全链路 Trace。每次 /api/agent 请求生成一个 trace，里面嵌套：
> - 每轮工具决策的 LLM generation（含 token 用量、延迟、成本）
> - 每个工具调用的 span（含 input args、output result）
> - 最终 synthesis 的 streaming generation
>
> 这套观测能力解决三类实际问题：
> ① **Latency 归因**：用户抱怨某个问题慢，瀑布图一目了然——是 DeepSeek 决策慢、还是 RAG 慢、还是某个 tool 慢；
> ② **Cost 监控**：每次调用的 token + DeepSeek 价格自动算，月度账单可预测；
> ③ **Bad case 分析**：失败/低质量回答可标 score，回头筛 trace 看是哪一步出问题——是工具误调用、tool 返回 error、还是 LLM 综合不当。
>
> 工程上做了**优雅降级**——没配 key 就 no-op，不破 user request。这是 ML 系统对'可观测性是可选项而非强依赖'的最佳实践。"

## 文件清单

```
backend/
├── app/
│   ├── observability.py     # Langfuse wrapper + no-op fallback
│   └── agent/core.py        # 已加 trace/span/generation 包裹
└── .env.example             # 已加 LANGFUSE_* 模板
```

## 下一步

Phase 3.5 — LangGraph 多 Agent。把当前的"单 Agent + 工具循环"拆成 Router / Planner / Executor / Reflector 状态机，加反思纠错闭环。
