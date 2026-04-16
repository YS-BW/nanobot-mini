"""配置管理"""

import hashlib
import os
from pathlib import Path


def _find_env_file() -> Path | None:
    """查找 .env 文件"""
    current = Path(__file__).parent.parent
    env_file = current / ".env"
    if env_file.exists():
        return env_file
    return None


def _load_env_file():
    """加载 .env 文件内容到环境变量"""
    env_path = _find_env_file()
    if env_path:
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    key, value = line.split("=", 1)
                    os.environ.setdefault(key.strip(), value.strip())


class Config:
    """应用配置"""

    def __init__(self):
        _load_env_file()

        # API 配置
        base_url = os.environ.get("BASE_URL", "https://api.openai.com/v1").rstrip("/")
        if base_url.endswith("/chat/completions"):
            base_url = base_url[:-17]
        self.base_url = base_url
        self.model = os.environ.get("LLM", "gpt-4o")
        self.api_key = os.environ.get("API_KEY", "")

        # 工作目录 = 当前命令执行目录
        self.workspace = Path.cwd().resolve()

        # 全局目录 ~/.bananabot/
        self.global_dir = Path.home() / ".bananabot"
        self.global_dir.mkdir(parents=True, exist_ok=True)

        # Sessions 目录
        self.sessions_dir = self.global_dir / "sessions"
        self.sessions_dir.mkdir(parents=True, exist_ok=True)

        # 项目记忆目录（按 cwd hash 隔离）
        self.memory_dir = self.global_dir / "projects" / self._hash_cwd() / "memory"
        self.memory_dir.mkdir(parents=True, exist_ok=True)

        # 迭代限制
        self.max_iterations = int(os.environ.get("MAX_ITERATIONS", "20"))

        # 上下文窗口大小
        self.context_window = int(os.environ.get("CONTEXT_WINDOW", "128000"))

        # Compact 阈值比例
        self.compact_threshold_round1 = float(os.environ.get("COMPACT_THRESHOLD_ROUND1", "0.70"))
        self.compact_threshold_round2 = float(os.environ.get("COMPACT_THRESHOLD_ROUND2", "0.85"))

    @staticmethod
    def _hash_cwd() -> str:
        """根据 cwd 生成项目 hash"""
        cwd = str(Path.cwd().resolve())
        return hashlib.md5(cwd.encode()).hexdigest()[:8]

    @classmethod
    def from_env(cls) -> "Config":
        """从环境变量创建配置"""
        return cls()
