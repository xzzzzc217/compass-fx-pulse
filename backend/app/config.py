import os
from pathlib import Path
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")


class Config:
    MYSQL_HOST = os.getenv("MYSQL_HOST", "127.0.0.1")
    MYSQL_PORT = int(os.getenv("MYSQL_PORT", "3306"))
    MYSQL_USER = os.getenv("MYSQL_USER", "root")
    MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "")
    MYSQL_DB = os.getenv("MYSQL_DB", "huaqi")

    # ---------- LLM defaults (used when role-specific not set) ----------
    LLM_PROVIDER = os.getenv("LLM_PROVIDER", "deepseek").lower()
    LLM_API_KEY = os.getenv("LLM_API_KEY", "")
    LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://api.deepseek.com/v1")
    LLM_MODEL = os.getenv("LLM_MODEL", "deepseek-chat")
    LLM_TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", "0.7"))
    LLM_MAX_TOKENS = int(os.getenv("LLM_MAX_TOKENS", "2048"))

    # ---------- /agent endpoint (Function Calling) ----------
    # Needs OpenAI tools support → must be a strong model (DeepSeek / GPT / Qwen-Plus etc.)
    LLM_AGENT_API_KEY = os.getenv("LLM_AGENT_API_KEY", LLM_API_KEY)
    LLM_AGENT_BASE_URL = os.getenv("LLM_AGENT_BASE_URL", LLM_BASE_URL)
    LLM_AGENT_MODEL = os.getenv("LLM_AGENT_MODEL", LLM_MODEL)

    # ---------- /ai endpoint (single-turn chat) ----------
    # Can be local LoRA (port 8001) for showcase; falls back to defaults if unset.
    LLM_CHAT_API_KEY = os.getenv("LLM_CHAT_API_KEY", LLM_API_KEY)
    LLM_CHAT_BASE_URL = os.getenv("LLM_CHAT_BASE_URL", LLM_BASE_URL)
    LLM_CHAT_MODEL = os.getenv("LLM_CHAT_MODEL", LLM_MODEL)

    SYSTEM_PROMPT = os.getenv(
        "SYSTEM_PROMPT",
        "你是 CompassFXPulse 的金融助手，专注外汇行情、汇率走势与外汇风险管理。\n"
        "重要原则：\n"
        "1. 你的训练数据有时间截止，不知道当前实时汇率与近期新闻。"
        "遇到\"今天/最近/当前汇率是多少\"这类问题时，请明确告诉用户："
        "\"我的训练数据无法获取实时行情，请前往本站\"历史汇率数据\"页面查看最新数据\"，"
        "切勿编造具体数值或波动区间。\n"
        "2. 回答外汇知识、风险管理、政策影响机制等\"原理性\"问题时，"
        "可以自由发挥你的知识储备。\n"
        "3. 涉及任何具体数字都要标注\"截至训练数据\"或类似时间限定。\n"
        "4. 简洁专业，不要营销语气。"
    )

    PORT = int(os.getenv("PORT", "8080"))
    DEBUG = os.getenv("DEBUG", "1") == "1"


settings = Config()
