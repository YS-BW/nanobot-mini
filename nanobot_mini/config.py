"""配置管理，支持 .env 文件"""
import os
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None


def _load_env():
    """加载 .env 文件（如果存在）"""
    env_path = Path(__file__).parent.parent / ".env"
    if env_path.exists() and load_dotenv:
        load_dotenv(env_path)


class Config:
    def __init__(self):
        _load_env()

        # 优先使用 MIMO 配置，否则用通用配置
        base = os.environ.get("MIMO_BASE_URL", os.environ.get("BASE_URL", "https://api.openai.com/v1")).rstrip("/")
        # 去除末尾的 /chat/completions，避免重复拼接
        if base.endswith("/chat/completions"):
            base = base[:-17]
        self.base_url = base
        self.model = os.environ.get("MIMO_LLM", os.environ.get("LLM", "gpt-4o"))
        self.api_key = os.environ.get("MIMO_API_KEY", os.environ.get("API_KEY", ""))

        # 其他配置
        self.workspace = os.environ.get("WORKSPACE", "/tmp/nanobot-mini")
        self.max_iterations = int(os.environ.get("MAX_ITERATIONS", "20"))

    @classmethod
    def from_env(cls):
        return cls()
