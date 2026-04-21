"""运行配置。

本模块负责把环境变量和 `.env` 文件收敛成一个统一配置对象。
配置对象在第一阶段重构后被视为基础设施能力，不应该散落在业务代码里直接读取。
"""

import os
from pathlib import Path

from .paths import default_global_dir, find_env_file


def _load_env_file() -> None:
    """把 `.env` 中的键值对加载到环境变量。

    这里使用 `setdefault`，意味着如果外部环境已经显式设置了某个变量，
    `.env` 不会覆盖它。
    """
    env_path = find_env_file()
    if not env_path:
        return
    with open(env_path, "r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip())


class Config:
    """应用运行配置。

    当前配置集中包含：
    - 模型地址与模型名
    - 工作目录
    - 全局目录与会话目录
    - compact 相关阈值
    - 最大迭代次数
    """

    def __init__(self):
        _load_env_file()

        base_url = os.environ.get("BASE_URL", "https://api.openai.com/v1").rstrip("/")
        if base_url.endswith("/chat/completions"):
            base_url = base_url[:-17]

        self.base_url = base_url
        self.model = os.environ.get("LLM", "gpt-4o")
        self.api_key = os.environ.get("API_KEY", "")
        self.workspace = Path.cwd().resolve()

        self.global_dir = default_global_dir()
        self.global_dir.mkdir(parents=True, exist_ok=True)

        self.sessions_dir = self.global_dir / "sessions"
        self.sessions_dir.mkdir(parents=True, exist_ok=True)

        self.max_iterations = int(os.environ.get("MAX_ITERATIONS", "20"))
        self.context_window = int(os.environ.get("CONTEXT_WINDOW", "128000"))
        self.compact_threshold_round1 = float(os.environ.get("COMPACT_THRESHOLD_ROUND1", "0.70"))
        self.compact_threshold_round2 = float(os.environ.get("COMPACT_THRESHOLD_ROUND2", "0.85"))

    @classmethod
    def from_env(cls) -> "Config":
        return cls()
