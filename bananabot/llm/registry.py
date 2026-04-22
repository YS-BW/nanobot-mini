"""模型与 provider 注册表。

这里把 LLM 层最基础的静态数据收回到一个文件：
- provider 固定规则
- 模型能力声明
- 模型档案
- provider / model 注册表

这样最基础的 provider / model 静态信息就不会再散落到多个文件里。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ProviderSpec:
    """描述一个受支持 provider 的固定元数据。"""

    name: str
    backend: str = "openai_compat"
    api_key_env: str = ""
    default_base_url: str = ""
    chat_path: str = "/chat/completions"
    supports_tools: bool = True
    supports_stream: bool = True
    supports_reasoning: bool = False
    requires_api_key: bool = True
    supports_system_prompt: bool = True
    extra_headers: dict[str, str] = field(default_factory=dict)
    default_query_params: dict[str, str] = field(default_factory=dict)
    default_extra_body: dict[str, Any] = field(default_factory=dict)


@dataclass
class ModelCapabilities:
    """描述模型能力，供上层界面和运行时判断。"""

    supports_stream: bool = True
    supports_tools: bool = True
    supports_reasoning: bool = False


@dataclass
class ModelProfile:
    """单个模型的完整调用档案。"""

    alias: str
    provider: str
    model: str
    base_url: str
    api_key: str = ""
    api_key_env: str = ""
    backend: str = "openai_compat"
    chat_path: str = "/chat/completions"
    headers: dict[str, str] = field(default_factory=dict)
    query_params: dict[str, str] = field(default_factory=dict)
    extra_body: dict[str, Any] = field(default_factory=dict)
    capabilities: ModelCapabilities = field(default_factory=ModelCapabilities)
    description: str = ""

    @property
    def label(self) -> str:
        """给界面层展示的人类可读标签。"""

        return self.description or f"{self.model} ({self.provider})"


DEFAULT_PROVIDER_SPECS: tuple[ProviderSpec, ...] = (
    ProviderSpec(
        name="dashscope",
        backend="dashscope",
        api_key_env="DASHSCOPE_API_KEY",
        default_base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        supports_reasoning=True,
    ),
    ProviderSpec(
        name="deepseek",
        backend="openai_compat",
        api_key_env="DEEPSEEK_API_KEY",
        default_base_url="https://api.deepseek.com",
    ),
    ProviderSpec(
        name="minimax",
        backend="openai_compat",
        api_key_env="MINIMAX_API_KEY",
        default_base_url="https://api.minimaxi.com/v1",
        supports_reasoning=True,
        default_extra_body={"reasoning_split": True},
    ),
    ProviderSpec(
        name="mimo",
        backend="openai_compat",
        api_key_env="MIMO_API_KEY",
        default_base_url="https://api.xiaomimimo.com/v1",
        supports_reasoning=True,
    ),
    ProviderSpec(
        name="local",
        backend="openai_compat",
        api_key_env="LOCAL_OMLX_API_KEY",
        default_base_url="http://127.0.0.1:8000/v1",
        supports_tools=False,
        requires_api_key=False,
    ),
)


class ProviderRegistry:
    """管理 provider 元数据。"""

    def __init__(self, specs: tuple[ProviderSpec, ...] | None = None):
        self._specs: dict[str, ProviderSpec] = {}
        for spec in specs or DEFAULT_PROVIDER_SPECS:
            self.register(spec)

    def register(self, spec: ProviderSpec) -> None:
        """注册单个 provider 规格。"""

        self._specs[spec.name] = spec

    def get(self, name: str) -> ProviderSpec:
        """按名称获取 provider 规格。"""

        try:
            return self._specs[name]
        except KeyError as exc:
            raise KeyError(f"Unknown provider: {name}") from exc

    def has(self, name: str) -> bool:
        """判断 provider 是否已登记。"""

        return name in self._specs

    def list_specs(self) -> list[ProviderSpec]:
        """返回全部 provider 规格。"""

        return [self._specs[key] for key in sorted(self._specs)]

    def list_names(self) -> list[str]:
        """返回全部 provider 名称。"""

        return sorted(self._specs)


class ModelRegistry:
    """管理模型别名与默认模型。"""

    def __init__(self, profiles: list[ModelProfile] | None = None, default_alias: str | None = None):
        self._profiles: dict[str, ModelProfile] = {}
        self.default_alias = default_alias
        for profile in profiles or []:
            self.register(profile)

        if self.default_alias is None and self._profiles:
            self.default_alias = next(iter(self._profiles))

    def register(self, profile: ModelProfile) -> None:
        """注册单个模型档案。"""

        if profile.alias in self._profiles:
            raise ValueError(f"Duplicate model alias: {profile.alias}")
        self._profiles[profile.alias] = profile
        if self.default_alias is None:
            self.default_alias = profile.alias

    def list_profiles(self) -> list[ModelProfile]:
        """按 alias 返回所有可用模型。"""

        return [self._profiles[key] for key in sorted(self._profiles)]

    def get(self, alias_or_model: str | None = None) -> ModelProfile:
        """按 alias 或真实模型名获取档案。"""

        target = alias_or_model or self.default_alias
        if not target:
            raise KeyError("No model configured")
        if target in self._profiles:
            return self._profiles[target]
        for profile in self._profiles.values():
            if profile.model == target:
                return profile
        raise KeyError(f"Unknown model: {target}")

    def has(self, alias_or_model: str) -> bool:
        """判断模型是否存在。"""

        try:
            self.get(alias_or_model)
        except KeyError:
            return False
        return True
