# Phase 2 工程笔记

> 这份文档记录 Phase 2（LoRA 微调 + Function Calling Agent）的设计决策、踩坑过程和最终方案。
> 设计目的：让面试时被问到任何细节都能答上来；不是"做了什么"，而是"为什么这么做、试过什么、最后怎么决定的"。

## 目标

把 CompassFXPulse 从"调 DeepSeek 的单轮 Web 应用"升级成：
1. **自训领域模型**：LoRA 微调 Qwen3-1.7B，专注外汇问答
2. **智能体应用**：Function Calling Agent，4 个工具，让 LLM 不再凭训练数据"瞎答"实时数值

对应蚂蚁 JD：
- 必备：Function Calling、Context Engineering、Prompt Engineering、Agent 框架
- 加分：SFT 经验、AI Infra（vLLM/Ollama 推理）、可展示的 RAG/Agent 项目

---

## 一、模型选型

| 候选 | 显存 (BF16) | 中英能力 | 时效 | 决定 |
|---|---|---|---|---|
| Qwen2.5-1.5B | 3.0 GB | ★★★ | 2024 | × 已被 Qwen3 超越 |
| **Qwen3-1.7B** | **3.4 GB** | **★★★★** | **2025** | **✓ 选定** |
| Qwen3-4B | 8.0 GB | ★★★★★ | 2025 | × 4060 8GB 训练放不下 LoRA + 激活 |
| DeepSeek-R1-Distill-Qwen-1.5B | 3.0 GB | ★★★ | 2025 | × 推理风格强，SFT 后易丢通用能力 |

**选 Qwen3-1.7B 的核心理由**：
1. 4060 8GB 能 BF16 训练（带 LoRA + 激活），不用上 4-bit 量化
2. 中文 SFT 数据下游能力恢复快（Qwen 团队中文优化好）
3. 支持 thinking 模式可选关闭（推理快，适合实时问答）

---

## 二、数据工程

总样本：**3194 条**（3035 训练 / 159 评测）

| 子集 | 规模 | 来源 | 作用 |
|---|---|---|---|
| `gbharti/finance-alpaca` | 3000（从 68912 中抽样） | HuggingFace | 通用金融能力底盘 |
| `zh_synth.jsonl` | 194 | 自合成（DeepSeek 标注） | 项目领域 / 中文专家口吻 |

**自合成的细节**（这块面试必问，要熟）：
- 50 个外汇主题 seed × 6 个角色变种（CFO / 散户 / 交易员 / 记者 / 机制 / 案例）
- DeepSeek-Chat 用 JSON-mode 生成 `{question, answer}`，温度 0.7
- system prompt 强制"不要编造具体数值"，只说定性 / 历史区间
- 单条成本 ~¥0.0025，全集 ~¥0.5

**为什么要混训**：
- 纯 finance-alpaca → 对中文外汇政策、A 股汇率联动答得不专业
- 纯自合成 → 数据量太小（200），LoRA 直接过拟合
- 混合后 finance-alpaca 提供"通用语感"，自合成提供"领域 voice"

---

## 三、训练超参

最终配置：
```python
LoRA:        r=16, alpha=32, dropout=0.05
Target:      q/k/v/o + gate/up/down (全 attn + MLP linear)
Batch:       per_device 2, grad_accum 8 → effective 16
Seq len:     512  (覆盖 ~95% 金融 Q&A，attn 计算砍 4x)
Epochs:      2   (3 epoch 在 200 zh 子集上易过拟合)
LR:          2e-4, cosine schedule, warmup 5%
Optimizer:   paged_adamw_8bit
Precision:   BF16 (sm_89 RTX 4060 原生支持)
Grad ckpt:   关闭（开启拖速 2x；8GB 无 ckpt 也能跑）
```

### 调优过程（踩过的坑，每个都是面试加分点）

#### 坑 1：trl 1.3.0 在 Windows 中文 locale 下崩溃
```
UnicodeDecodeError: 'gbk' codec can't decode byte 0x9c
```
trl 用 `Path.read_text()` 默认编码读 jinja 模板，Windows 中文 locale 下用 GBK 读 UTF-8 文件失败。
**修法**：环境变量 `PYTHONUTF8=1` 强制 Python I/O 用 UTF-8。

#### 坑 2：4-bit 量化反而慢
4-bit NF4 实测每步 28 秒，BF16 全精度每步 20 秒。
原因：8GB 显存够装 BF16，量化的 dequantize-on-forward 反而成开销。
**结论**：量化是为节省显存，不是加速。显存够时不要量化。

#### 坑 3：Gradient Checkpointing 速度税
开 grad ckpt 每步 20 秒，关掉每步 10 秒，但 batch 4 关掉就 OOM。
**修法**：batch 砍半（2），grad_accum 翻倍（8），有效 batch 不变；activation 内存砍半，grad ckpt 可关。
最终 10 秒/步，3 倍提速。

#### 数字总结
| 配置 | 每步耗时 | 全程 (380 步) |
|---|---|---|
| 4-bit + bs=4 + grad_ckpt + seq 1024 | 28s | ~3 小时 |
| BF16 + bs=4 + grad_ckpt + seq 512 | 20s | ~2 小时 |
| **BF16 + bs=2/ga=8 + no grad_ckpt + seq 512** | **10s** | **~65 分钟** |

---

## 四、推理部署

### 为什么不用 vLLM
vLLM 官方 Linux only。Windows 上要装得通过 WSL2，部署链路复杂。
**方案**：FastAPI + transformers，自己写 OpenAI 兼容 `/v1/chat/completions`。
**优点**：
1. 主项目跑在 Windows 原生，零依赖 WSL
2. 协议层 OpenAI 兼容，未来要切 vLLM 只改 `LLM_BASE_URL`，**零业务代码改动**
3. 支持 SSE 流式输出，与现有前端无缝对接

### 切换流程
```
backend/.env
  LLM_PROVIDER=local-lora
  LLM_BASE_URL=http://127.0.0.1:8001/v1
  LLM_MODEL=qwen3-1.7b-finance
```
重启后端，前端 AI 问答就走自训模型。完全可逆。

---

## 五、Function Calling Agent

### 工具清单（4 个）
| 工具 | 输入 | 输出 | 后端实现 |
|---|---|---|---|
| `get_exchange_rate` | currency_a/b, [date] | 单点汇率 | SQL on `historicaldata` |
| `get_rate_range` | currency_a/b, start, end | min/max/mean/stdev/change% | SQL + Python 统计 |
| `predict_exchange_rate` | currency_a/b, horizon | 预测序列 | SQL on `predictdata`（Phase 3 接 TimeXer） |
| `calculate_var` | currency_a/b, amount, conf, horizon | VaR + 解释 | 历史波动率 → delta-normal |

### Agent 循环设计
```
user → LLM (with tools)
       ↓
       tool_calls?
       ↙        ↘
      yes        no → stream final answer
       ↓
   execute tools  →  append results to messages
       ↓
   loop（最多 4 轮）
```

### 关键设计决策
1. **Trace 事件**：每步规划/调用都通过 SSE 暴露给前端，可视化 "Agent 推理步骤"——这是 demo 时的核心差异化
2. **拒绝过度调用**：system prompt 明确"机制原理类问题不要调用工具"，避免 LLM 习惯性 tool-call
3. **错误透传**：工具返回 error 直接给 LLM，让它如实告诉用户"系统中无此数据"，而不是编造
4. **轮次上限**：MAX_TOOL_ROUNDS=4 防止无限循环

### 前后端接口
```
GET /api/agent?query=...&trace=1
SSE 事件流：
  data: {"trace": {"kind": "plan", "round": 1, "tools": ["get_exchange_rate"]}}
  data: {"trace": {"kind": "tool_result", "name": "...", "args": {...}, "result": {...}}}
  data: {"text": "根据系统数据..."}  ← LLM 流式综合
  data: {"text": "[DONE]"}
```

---

## 六、面试讲法（30 秒电梯版）

> "原项目是花旗杯的外汇 Web 应用，用 DeepSeek 做 AI 问答——但发现 LLM 会编造实时汇率数值，因为训练截止在 2025 年。
>
> Phase 2 我做了两件事：
> ① **自训领域模型**：基于 Qwen3-1.7B 用 LoRA 微调金融问答能力。混训 finance-alpaca 3K 条 + 用 DeepSeek 自合成 200 条中文外汇 Q&A。在 4060 8GB 上调到 BF16 + 关 grad ckpt + bs=2/ga=8 这套配置，单卡 65 分钟训完。然后用 FastAPI 包装成 OpenAI 兼容服务，主后端只改 .env 一行就能切到自训模型。
>
> ② **Function Calling Agent**：定义 4 个工具——汇率查询、范围统计、预测、VaR 计算。让 LLM 自己决定调用哪个，不再凭训练数据回答。前端做了 Trace 可视化，能实时看到 Agent 的规划和工具调用结果。
>
> 这套架构对应了蚂蚁 JD 里的 Function Calling、Context Engineering、SFT、AI Infra（推理服务）几个核心要求。"

## 七、可展开的细节问题（面试官常问）

### Q：为什么 LoRA r=16？
A：经验值。Qwen3-1.7B 的 hidden size 是 2048，r=16 让每个 LoRA 矩阵参数量约 2048×16×2=65K，全部 7 个 target × 28 layer ≈ 12M 可训练参数，约占总参数 0.7%。再大（r=32/64）训练速度变慢但效果增益不显著（PEFT 论文 Fig.5 拐点）；再小（r=8）会欠拟合中文领域分布。

### Q：怎么知道有没有过拟合？
A：eval set 上看 loss——eval_loss 持续下降说明还在学；如果 train_loss 下降但 eval_loss 反弹就过拟合。我设了 eval_steps=100，全程 4 个 eval point，足够看出趋势。

### Q：DeepSeek 已经够强了，为什么还要自训一个 1.7B？
A：三个理由：
1. **隐私**：金融数据不出本地（蚂蚁很关心）
2. **延迟 / 成本**：本地推理 30+ tok/s 零成本 vs DeepSeek 每次 ¥0.001
3. **领域 voice**：自训模型的回答更"项目化"，能用我们项目里的术语和语气

### Q：自合成数据怎么保证质量？
A：用更强的 DeepSeek 当标注模型（distillation 思路），强制 JSON output，prompt 里禁止编造具体数值。但这只是 weak supervision，所以只占总数据 6%，不会主导模型行为。Phase 3 会引入人工 spot-check + LLM-as-Judge 评估自合成集质量。

### Q：Function Calling 怎么避免 LLM 乱调用工具？
A：三个机制：
1. system prompt 显式区分"工具问题 vs 知识问题"
2. 工具描述 description 写得严谨，模糊的工具更容易被乱选
3. 后端跑 `tests/test_agent.py`，5 个 case 包含 1 个"应该不调用"的 case 做回归

### Q：vLLM 你只是说不能用 Windows，那怎么证明你了解它？
A：vLLM 核心是 PagedAttention（KV cache 分页管理）+ continuous batching + 异步 scheduling。我知道它怎么工作，未来如果迁到云上 Linux 会切过去——这也是为什么我现在自己写 serve.py 时坚持 OpenAI 兼容协议，就是为切换零成本。

### Q：Phase 3 计划是什么？
A：① 引入 RAG（央行政策 + 项目爬虫新闻 → bge-m3 + Qdrant + 重排）；② 把 4 个工具暴露成 MCP Server，让 Cursor / Claude Desktop 能直接调用；③ 多 Agent 编排（LangGraph），加 Reflector 做反思纠错；④ 接 Langfuse 做全链路 Trace + 100 题 LLM-as-Judge 评测集。
