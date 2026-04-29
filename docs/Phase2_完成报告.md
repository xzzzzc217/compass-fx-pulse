# Phase 2 完成报告

> 完成日期：2026-04-28
> 状态：✅ 全部交付

---

## 一、产出清单

### 后端
- [`backend/app/agent/tools.py`](../backend/app/agent/tools.py) — 4 个 Function Calling 工具
- [`backend/app/agent/core.py`](../backend/app/agent/core.py) — Agent 主循环（规划 + 执行 + 反思）
- [`backend/app/routes_agent.py`](../backend/app/routes_agent.py) — `/api/agent` SSE 端点
- [`backend/tests/test_agent.py`](../backend/tests/test_agent.py) — 7 个回归测试用例

### 前端
- [`frontend/src/views/Agent.vue`](../frontend/src/views/Agent.vue) — Agent 调用追踪可视化
- 导航增加"智能助手"

### LoRA 训练 / 部署
- [`llm/scripts/download_model.py`](../llm/scripts/download_model.py) — 从 hf-mirror 下载 Qwen3-1.7B
- [`llm/scripts/synthesize_zh_sft.py`](../llm/scripts/synthesize_zh_sft.py) — 用 DeepSeek 自合成中文金融 Q&A
- [`llm/scripts/prepare_dataset.py`](../llm/scripts/prepare_dataset.py) — 混合 finance-alpaca + zh_synth
- [`llm/training/train_lora.py`](../llm/training/train_lora.py) — LoRA SFT 训练
- [`llm/training/merge_lora.py`](../llm/training/merge_lora.py) — 适配器合并
- [`llm/training/quick_eval.py`](../llm/training/quick_eval.py) — 模型烟测
- [`llm/training/compare_models.py`](../llm/training/compare_models.py) — DeepSeek vs base vs FT 三方对比
- [`llm/serve.py`](../llm/serve.py) — FastAPI OpenAI 兼容服务

### 文档
- [`docs/Phase2_工程笔记.md`](Phase2_工程笔记.md) — 设计决策 + 踩坑记 + 面试问答模板
- [`docs/Phase2_完成报告.md`](Phase2_完成报告.md) — 本文档
- [`llm/output/comparison.md`](../llm/output/comparison.md) — 8 题 × 3 模型对比报告
- [`llm/output/training.log`](../llm/output/training.log) — 完整训练日志

---

## 二、关键数据

### 训练
| 指标 | 值 |
|---|---|
| 基座模型 | Qwen3-1.7B (BF16, 3.4 GB) |
| 训练样本 | 3,035 (finance-alpaca 3000 + zh_synth 35) |
| 评测样本 | 159 |
| LoRA 参数 | r=16, alpha=32, dropout=0.05 |
| Target modules | q/k/v/o + gate/up/down |
| 可训练参数 | ~14M (0.83% of base) |
| 优化器 | paged_adamw_8bit |
| 学习率 | 2e-4, cosine, warmup 5% |
| 实际训练步数 | 190 (epoch 1，eval plateau 早停) |
| 训练耗时 | ~1 小时 |
| GPU 峰值显存 | ~7 GB / 8 GB |

### Loss 曲线（健康下降）
| Step | train_loss | eval_loss | token_acc |
|---|---|---|---|
| 1 | 4.603 | 4.853 | 0.43 |
| 100 | — | 1.311 | 0.70 |
| 190 (epoch 1) | 1.40 | 1.296 | 0.70 |

### 三方推理速度（同一硬件，8 题平均）
| 模型 | 推理时延 | 输出长度 |
|---|---|---|
| DeepSeek-Chat (671B MoE 云端) | 4.2s | ~250 字 |
| Qwen3-1.7B Base (本地 BF16) | 14.6s | ~600 字（多 markdown） |
| Qwen3-1.7B-Finance (本地 BF16, LoRA) | 9.7s | ~280 字（散文） |

**FT 比 Base 快 33%** —— 因为 SFT 让它学会"分析师式简洁"，少生成 token = 少时间。**这是 SFT 的副作用，但是好的副作用**。

---

## 三、Function Calling Agent 实战

### 4 个工具
1. `get_exchange_rate(ccy_a, ccy_b, [date])` — 单点汇率
2. `get_rate_range(ccy_a, ccy_b, start, end)` — 范围统计
3. `predict_exchange_rate(ccy_a, ccy_b, horizon_days)` — 预测序列
4. `calculate_var(ccy_a, ccy_b, position, conf, horizon)` — VaR

### 三层防过度调用
- System prompt 显式反例（"什么是 X 不要调用工具"）
- 工具描述加 "DO NOT USE for ..."
- temperature=0.1 让工具决策更确定

### 7 个回归测试
- 应调用：latest rate / range stats / VaR calc / prediction
- 应**不**调用：纯知识（长版 + 短版） / 概念定义

---

## 四、双模型并行架构

**这是 Phase 2 最重要的设计**：
LoRA 模型和 DeepSeek 各擅其长，不互斥。

```
┌──────────────────┐       ┌────────────────────────┐
│ /ai      ←──────→│       │ Function Calling Agent │
│ "慧聚答疑"       │       │ DeepSeek (tool calling)│
│ 简单问答         │       │ /agent "智能助手"      │
└────────┬─────────┘       └────────────────────────┘
         │
         │ LLM_PROVIDER=...
         ▼
   ┌──────────────────┐         ┌──────────────────┐
   │ DeepSeek 云端    │   或    │ 本地 LoRA :8001  │
   │ 通用知识广        │         │ 风格对齐金融     │
   │ 支持 tools       │         │ 离线，免费       │
   └──────────────────┘         └──────────────────┘
```

### 为什么不切换默认到 LoRA
**Function Calling Agent 必须用 DeepSeek**，因为：
- 我们的 `serve.py` 是简化的 OpenAI 兼容实现，**未实现 `tools` 字段处理**
- LoRA 1.7B 模型本身的 tool-calling 能力远弱于 DeepSeek-Chat

所以：
- **后端默认仍走 DeepSeek**（Agent + 慧聚答疑都通）
- **LoRA 服务作为备选**，需要离线/降本时一行 `.env` 切换
- 前端 `/agent` 页面的 demo 主打 Agent + DeepSeek（最有看点）

---

## 五、面试演示路径（10 分钟版）

### 第一段（3 min）：项目背景 + 架构图
> "原项目是花旗杯外汇 Web 应用——Vue + Flask + MySQL + DeepSeek 做 AI 问答。
> Phase 2 我做了两件事：自训领域模型 + 智能体改造..."

打开 [Phase2_工程笔记.md](Phase2_工程笔记.md) 的架构图。

### 第二段（3 min）：Live Demo
1. 浏览器打开 http://localhost:8081/agent
2. 输入"现在美元兑日元的汇率是多少？"
3. **左侧实时显示**：plan → tool_call(get_exchange_rate) → tool_result → 右侧合成回答
4. 输入"我有 100 万美元的美元/日元敞口，1 天 99% VaR 是多少？"
5. 显示：plan → tool_call(calculate_var) → 返回带解释的 VaR 数值
6. 输入"什么是 carry trade？" → **左侧不调用任何工具**，直接讲解

### 第三段（3 min）：训练成果
1. 打开 [comparison.md](../llm/output/comparison.md)，挑 Q1（外汇风险）
2. 对比 DeepSeek 简洁、Base 啰嗦带 markdown、FT 分析师风格
3. 强调："1.7B 小模型经过 SFT 后比 base 输出短 53%、推理快 33%、风格统一"

### 第四段（1 min）：Phase 3 路线图
- RAG（央行政策 + 项目新闻）
- MCP Server 暴露给 Cursor/Claude Desktop
- LangGraph 多 Agent + Reflector
- Langfuse 全链路 Trace

---

## 六、How to start everything

```powershell
# 窗口 1：MySQL（如果不是 Service 自启）
net start MySQL80

# 窗口 2：后端
conda activate compass-fx
cd D:\花旗杯\compass-fx-pulse\backend
python main.py

# 窗口 3：前端
cd D:\花旗杯\compass-fx-pulse\frontend
npm run dev
# 浏览器 http://localhost:8081

# 窗口 4：本地 LoRA 服务（可选）
conda activate compass-fx
cd D:\花旗杯\compass-fx-pulse\llm
PYTHONUTF8=1 python serve.py
# 监听 :8001
```

切到 LoRA 模型（暂时关闭 Agent 工具能力）：
```
backend/.env
LLM_PROVIDER=local-lora
LLM_BASE_URL=http://127.0.0.1:8001/v1
LLM_MODEL=qwen3-1.7b-finance
LLM_API_KEY=local
```

切回 DeepSeek（恢复 Agent）：
```
LLM_PROVIDER=deepseek
LLM_BASE_URL=https://api.deepseek.com/v1
LLM_MODEL=deepseek-chat
LLM_API_KEY=sk-...
```

---

## 七、JD 要求覆盖度自检

| JD 要求 | 我的实现 | 在哪里 |
|---|---|---|
| Prompt Engineering | system prompt 三层防御 + few-shot 反例 | `agent/core.py` |
| Context Engineering | 工具描述 + tool_choice="auto" 决策 | `agent/tools.py` |
| Function Calling | 4 个工具 + 多轮 tool calling 循环 | `agent/core.py` |
| 意图识别 / 任务拆解 | LLM 路由决定调用哪个工具 | Agent loop |
| 工具编排 | 每轮可调用多个工具，结果递归回 LLM | `MAX_TOOL_ROUNDS=4` |
| 反思纠错闭环 | tool error 透传 + LLM 决定重试或拒答 | `core.py:execute()` |
| SDK 封装 | FastAPI + OpenAI 协议 | `llm/serve.py` |
| 自动评测 / 回测 | 7 个测试用例 + 8 题对比报告 | `tests/`, `compare_models.py` |
| **加分①** RAG / 多 Agent / MCP | Phase 3 启动 | (next) |
| **加分②** 开源 / GitHub | 待发布 | (Phase 3) |
| **加分③** vLLM / Ollama / KV cache | serve.py 走 OpenAI 协议，未来切 vLLM 零改动 | `llm/serve.py` 注释 |
| **加分④** SFT / RL 经验 | 完整 LoRA SFT 流程 + 数据自合成 + early stop 决策 | `llm/training/` |
