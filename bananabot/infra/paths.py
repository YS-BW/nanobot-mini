"""通用路径辅助函数。"""

from pathlib import Path


def project_root() -> Path:
    """推断仓库根目录。"""

    return Path(__file__).resolve().parents[2]


def default_global_dir() -> Path:
    """返回默认全局目录。"""

    return Path.home() / ".bananabot"


def find_env_file(root: Path | None = None) -> Path | None:
    """查找仓库根目录下的 `.env` 文件。"""

    candidate = (root or project_root()) / ".env"
    return candidate if candidate.exists() else None


def find_models_file(root: Path | None = None) -> Path | None:
    """查找仓库根目录下的 `models.toml` 文件。"""

    candidate = (root or project_root()) / "models.toml"
    return candidate if candidate.exists() else None
