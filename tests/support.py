"""测试期的模块加载辅助函数。"""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_ROOT = REPO_ROOT / "bananabot"


def ensure_namespace_package(name: str, path: Path) -> types.ModuleType:
    """构造一个最小 namespace package，避免触发坏掉的包入口。"""

    module = sys.modules.get(name)
    if module is None:
        module = types.ModuleType(name)
        module.__path__ = [str(path)]
        sys.modules[name] = module
    return module


def load_repo_module(module_name: str, relative_path: str):
    """直接按文件路径加载仓库内模块，并注册到 `sys.modules`。"""

    ensure_namespace_package("bananabot", PACKAGE_ROOT)

    module_path = REPO_ROOT / relative_path
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"无法加载模块: {module_name} <- {module_path}")

    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module
