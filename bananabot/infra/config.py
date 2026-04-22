"""运行配置。"""

from __future__ import annotations

import os
import tomllib
from pathlib import Path
from typing import Any

from ..llm import (
    ModelCapabilities,
    ModelProfile,
    ModelRegistry,
    ProviderRegistry,
)
from .paths import default_global_dir, find_env_file, find_models_file


class ConfigError(ValueError):
    """配置加载失败。"""


def _read_env_file() -> tuple[Path | None, dict[str, str]]:
    """读取 `.env` 键值对，不污染全局环境变量。"""

    env_path = find_env_file()
    if not env_path:
        return None, {}

    values: dict[str, str] = {}
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return env_path, values


def _read_models_config() -> tuple[Path | None, dict[str, Any]]:
    """读取 `models.toml`。"""

    models_path = find_models_file()
    if not models_path:
        return None, {}
    with open(models_path, "rb") as handle:
        return models_path, tomllib.load(handle)


class Config:
    """应用运行配置。"""

    def __init__(self):
        self.env_file, self.env_values = _read_env_file()
        self.models_file, self.models_config = _read_models_config()
        if not self.models_file:
            raise ConfigError("缺少 models.toml，当前版本必须通过 models.toml 声明模型")
        self.provider_registry = ProviderRegistry()

        self.workspace = Path.cwd().resolve()

        self.global_dir = default_global_dir()
        self.global_dir.mkdir(parents=True, exist_ok=True)

        self.sessions_dir = self.global_dir / "sessions"
        self.sessions_dir.mkdir(parents=True, exist_ok=True)
        self.runtime_state_dir = self.global_dir / "runtime-state"
        self.runtime_state_dir.mkdir(parents=True, exist_ok=True)

        self.max_iterations = int(self._env_get("MAX_ITERATIONS", "20"))
        self.context_window = int(self._env_get("CONTEXT_WINDOW", "128000"))
        self.compact_threshold_round1 = float(self._env_get("COMPACT_THRESHOLD_ROUND1", "0.70"))
        self.compact_threshold_round2 = float(self._env_get("COMPACT_THRESHOLD_ROUND2", "0.85"))

        self.model_registry = self._build_model_registry()
        self.model_alias = self.model_registry.default_alias or ""
        current = self.model_registry.get(self.model_alias)
        self.base_url = current.base_url
        self.model = current.model
        self.api_key = current.api_key

    def _env_get(self, key: str, default: str = "") -> str:
        """读取环境变量，优先级为系统环境变量 > `.env`。"""

        return os.environ.get(key, self.env_values.get(key, default))

    @staticmethod
    def _truthy(value: Any, default: bool = False) -> bool:
        """把 toml / env 布尔值统一成 bool。"""

        if value is None:
            return default
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "yes", "on"}
        return bool(value)

    def _build_capabilities(self, provider: str, data: dict[str, Any]) -> ModelCapabilities:
        """合并 provider 默认能力与模型覆盖。"""

        spec = self.provider_registry.get(provider)
        return ModelCapabilities(
            supports_stream=self._truthy(data.get("supports_stream"), spec.supports_stream),
            supports_tools=self._truthy(data.get("supports_tools"), spec.supports_tools),
            supports_reasoning=self._truthy(data.get("reasoning"), spec.supports_reasoning),
        )

    def _profile_from_toml(self, name: str, data: dict[str, Any]) -> ModelProfile:
        """从 `models.toml` 条目构造模型档案。"""

        provider = data.get("provider")
        if not provider:
            raise ConfigError(f"models.toml 条目缺少 provider: {name}")
        if not self.provider_registry.has(provider):
            raise ConfigError(f"models.toml 使用了未知 provider: {provider}")

        spec = self.provider_registry.get(provider)
        alias = data.get("alias", name)
        base_url = str(data.get("base_url") or spec.default_base_url).rstrip("/")
        if not base_url:
            raise ConfigError(f"模型缺少 base_url: {alias}")

        model_name = data.get("model")
        if not model_name:
            raise ConfigError(f"模型缺少 model 字段: {alias}")

        api_key_env = data.get("api_key_env") or spec.api_key_env
        api_key = self._env_get(api_key_env) if api_key_env else ""
        if not api_key:
            api_key = str(data.get("api_key", "")).strip()

        headers = dict(spec.extra_headers)
        headers.update(dict(data.get("headers", {})))
        query_params = dict(spec.default_query_params)
        query_params.update(dict(data.get("query_params", {})))
        extra_body = dict(spec.default_extra_body)
        extra_body.update(dict(data.get("extra_body", {})))

        return ModelProfile(
            alias=alias,
            provider=provider,
            backend=data.get("backend", spec.backend),
            model=model_name,
            base_url=base_url,
            api_key=api_key,
            api_key_env=api_key_env,
            chat_path=data.get("chat_path", spec.chat_path),
            headers=headers,
            query_params=query_params,
            extra_body=extra_body,
            capabilities=self._build_capabilities(provider, data),
            description=data.get("description", alias),
        )

    def _build_model_registry_from_toml(self) -> ModelRegistry:
        """从 `models.toml` 构造模型注册表。"""

        models_section = self.models_config.get("models", {}) if self.models_config else {}
        if not models_section:
            raise ConfigError("models.toml 缺少 [models] 配置")

        profiles: list[ModelProfile] = []
        skipped_profiles: dict[str, str] = {}
        for name, data in models_section.items():
            profile = self._profile_from_toml(name, data)
            spec = self.provider_registry.get(profile.provider)
            if spec.requires_api_key and not profile.api_key:
                env_name = profile.api_key_env or spec.api_key_env or "未声明"
                skipped_profiles[profile.alias] = f"缺少密钥: {env_name}"
                continue
            profiles.append(profile)

        if not profiles:
            detail = ", ".join(f"{alias}({reason})" for alias, reason in skipped_profiles.items())
            raise ConfigError(f"没有可用模型，{detail or '请检查 models.toml 和 .env'}")

        default_alias = self._env_get("DEFAULT_MODEL") or self.models_config.get("meta", {}).get("default_model")
        registry = ModelRegistry(profiles, default_alias=default_alias)
        if default_alias:
            if default_alias in skipped_profiles:
                raise ConfigError(f"默认模型 {default_alias} 不可用：{skipped_profiles[default_alias]}")
            if not registry.has(default_alias):
                raise ConfigError(f"默认模型 {default_alias} 未出现在可用模型列表中")
        return registry

    def _build_model_registry(self) -> ModelRegistry:
        """按当前白名单和 `models.toml` 构造模型注册表。"""

        return self._build_model_registry_from_toml()

    @classmethod
    def from_env(cls) -> "Config":
        return cls()
