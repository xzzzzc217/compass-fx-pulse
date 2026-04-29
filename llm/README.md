# LoRA Fine-tuning + Local Serving

Fine-tune Qwen3-1.7B on the CompassFX finance corpus, deploy as an OpenAI-compatible
local API, hot-swap into the main backend by changing `.env`.

## 目录

```
llm/
├── data/
│   ├── zh_synth.jsonl       自合成中文金融 SFT，由 synthesize_zh_sft.py 产出
│   ├── train.jsonl          训练集（chat 格式），由 prepare_dataset.py 合并产出
│   └── eval.jsonl           评测集（同上）
├── models/
│   └── Qwen3-1.7B/          基座模型，由 download_model.py 下载
├── output/
│   ├── lora-qwen3-1.7b/     LoRA 训练 checkpoint
│   └── qwen3-1.7b-finance-merged/    merge 后的全权重模型
├── scripts/
│   ├── download_model.py    从 hf-mirror.com 拉 Qwen3-1.7B
│   ├── synthesize_zh_sft.py 用 DeepSeek 自合成 200+ 中文金融 Q&A
│   └── prepare_dataset.py   合并 finance-alpaca + zh_synth → train/eval JSONL
├── training/
│   ├── train_lora.py        4-bit NF4 + LoRA r=16 训练
│   ├── merge_lora.py        把 LoRA 适配器合并回基座
│   └── quick_eval.py        合并后小烟测，5 个固定 prompt
├── serve.py                 FastAPI + transformers 的 OpenAI 兼容服务
├── requirements.txt
└── README.md (this file)
```

## 端到端流程

### 第一次走完（一次性）

```powershell
conda activate compass-fx
cd D:\花旗杯\compass-fx-pulse\llm

# 0. 装 llm 子项目额外依赖（PyTorch 等已装）
python -m pip install -r requirements.txt

# 1. 下载基座 Qwen3-1.7B（约 3.4 GB，5-10 分钟）
python scripts\download_model.py

# 2. 合成中文金融 Q&A（200 条 ≈ 5 分钟，DeepSeek 调用 ¥0.5）
python scripts\synthesize_zh_sft.py 200

# 3. 合并数据集（finance-alpaca 抽 3000 条 + 200 条中文）
python scripts\prepare_dataset.py

# 4. LoRA 训练（4060 上 2-3 小时，3 epoch）
python training\train_lora.py

# 5. 合并适配器到基座（5 分钟）
python training\merge_lora.py

# 6. 烟测一下基座 vs 微调对比
python training\quick_eval.py base       # 基座答案
python training\quick_eval.py            # 微调后答案
```

### 部署成本地推理服务

```powershell
# 在新窗口（保持后端 + 前端跑着）
conda activate compass-fx
cd D:\花旗杯\compass-fx-pulse\llm
python serve.py
# 监听 127.0.0.1:8001，OpenAI 兼容
```

测一下：
```powershell
curl.exe -X POST http://127.0.0.1:8001/v1/chat/completions `
    -H "Content-Type: application/json" `
    -d "{\"model\":\"qwen3-1.7b-finance\",\"messages\":[{\"role\":\"user\",\"content\":\"什么是carry trade?\"}]}"
```

### 切换到 Compass 后端用

修改 `backend/.env`：
```
LLM_PROVIDER=local-lora
LLM_BASE_URL=http://127.0.0.1:8001/v1
LLM_MODEL=qwen3-1.7b-finance
LLM_API_KEY=local-no-auth-needed
```

重启 `python backend/main.py`，前端 AI 问答就走你自己微调的模型了。
切回 DeepSeek 只需把上面 4 行改回原值。

## 为什么这么设计

| 决策 | 选择 | 原因 |
|---|---|---|
| 基座模型 | **Qwen3-1.7B** | 4060 8GB 能 FP16 推理；中英双语；2025 年模型，没过时 |
| 微调方法 | **QLoRA (4-bit NF4)** | 显存压到 ~5 GB；JD 加分项里写明 SFT |
| LoRA 参数 | r=16, alpha=32, dropout=0.05 | r=16 是 1.7B 模型的 sweet spot；alpha=2r 是 PEFT 论文经验值 |
| Target | 全部 attn + MLP linear | Qwen 系列实测全 linear 收敛更稳 |
| 训练框架 | **trl 1.3 SFTTrainer** | 自动处理 chat template；ChatML 格式开箱即用 |
| 数据集 | finance-alpaca + 自合成 | 通用金融 + 项目领域，2:1 是经验混比 |
| 推理服务 | **FastAPI + transformers** | Windows 原生跑；vLLM 仅支持 Linux |
| API 协议 | **OpenAI Chat Completions** | 后端 LLM 客户端零修改即可切换 |

## 故障排查

### 训练时 OOM
降 batch_size：
```
python training\train_lora.py --batch_size 2 --grad_accum 8
```

### 训练 loss 不降
- 检查 `data/train.jsonl` 头几条格式是否正确
- LR 改成 1e-4 试试
- 用 wandb 看 loss 曲线：`pip install wandb && wandb login`，把 `report_to="none"` 改成 `"wandb"`

### 推理服务 OOM
serve.py 默认 BF16 全量，约 3.4 GB。如果还 OOM 加：
```python
# serve.py 中 _load() 内
_model = AutoModelForCausalLM.from_pretrained(
    str(path),
    torch_dtype=torch.bfloat16,
    device_map="auto",
    quantization_config=BitsAndBytesConfig(load_in_4bit=True),  # 加这行
    ...
)
```

### Phase 3 起的迁移路径
当我们做 Function Calling Agent 时，可以考虑：
- 把 serve.py 升级到支持 OpenAI tools API（追加 `tool_calls` 字段处理）
- 或者干脆改用 vLLM（在 WSL2 内）：性能更高且原生支持 function calling
