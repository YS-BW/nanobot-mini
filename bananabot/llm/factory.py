"""Provider 工厂。"""

from __future__ import annotations

from .registry import ModelProfile
from .providers import DashScopeProvider, OpenAICompatProvider
from .providers.base import BaseProvider


class ProviderFactory:
    """按 backend 创建 provider 实现。"""

    def __init__(self):
        self._providers: dict[str, BaseProvider] = {
            "openai_compat": OpenAICompatProvider(),
            "dashscope": DashScopeProvider(),
        }

    def create(self, profile: ModelProfile) -> BaseProvider:
        """根据模型档案返回对应 provider。"""

        backend = profile.backend or "openai_compat"
        try:
            return self._providers[backend]
        except KeyError as exc:
            raise KeyError(f"Unknown provider backend: {backend}") from exc

    def list_backends(self) -> list[str]:
        """列出当前可用 backend。"""

        return sorted(self._providers)
