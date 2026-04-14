"""配置管理"""

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


def _get_default_workspace() -> Path:
    """获取默认工作目录"""
    return Path.home() / ".nanobot" / "workspace"


def _ensure_workspace(workspace: Path) -> Path:
    """确保工作目录存在"""
    workspace.mkdir(parents=True, exist_ok=True)
    return workspace


class Config:
    """应用配置"""

    def __init__(self):
        _load_env_file()

        # API 配置
        base_url = os.environ.get("BASE_URL", "https://api.openai.com/v1").rstrip("/")
        # 去除末尾的 /chat/completions，避免重复拼接
        if base_url.endswith("/chat/completions"):
            base_url = base_url[:-17]
        self.base_url = base_url
        self.model = os.environ.get("LLM", "gpt-4o")
        self.api_key = os.environ.get("API_KEY", "")

        # 工作目录（默认 ~/.nanobot/workspace，支持环境变量覆盖）
        workspace_path = os.environ.get("WORKSPACE", str(_get_default_workspace()))
        self.workspace = _ensure_workspace(Path(workspace_path).expanduser())

        # 迭代限制
        self.max_iterations = int(os.environ.get("MAX_ITERATIONS", "20"))

    @classmethod
    def from_env(cls) -> "Config":
        """从环境变量创建配置"""
        return cls()
