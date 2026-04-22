"""多 provider LLM 客户端。"""

from __future__ import annotations

import asyncio

import httpx

from .factory import ProviderFactory
from .registry import ModelRegistry
from .types import LLMResponse


class LLMClient:
    """统一的多模型调用入口。"""

    def __init__(
        self,
        *,
        model_registry: ModelRegistry,
        provider_factory: ProviderFactory | None = None,
        default_model: str | None = None,
        timeout_seconds: float = 120,
        max_retries: int = 3,
    ):
        self.model_registry = model_registry
        self.provider_factory = provider_factory or ProviderFactory()
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self.model_alias = default_model or model_registry.default_alias or ""
        if not self.model_alias:
            raise ValueError("LLMClient requires at least one configured model")
        self._sync_current_profile()

    def _sync_current_profile(self) -> None:
        """同步当前模型快照。"""

        profile = self.get_current_profile()
        self.base_url = profile.base_url
        self.api_key = profile.api_key
        self.model = profile.model

    def get_current_profile(self):
        """返回当前模型档案。"""

        return self.model_registry.get(self.model_alias)

    def get_model_alias(self) -> str:
        """返回当前模型 alias。"""

        return self.model_alias

    def set_model(self, alias_or_model: str):
        """切换当前默认模型。"""

        profile = self.model_registry.get(alias_or_model)
        self.model_alias = profile.alias
        self._sync_current_profile()
        return profile

    def list_models(self):
        """返回所有可用模型。"""

        return self.model_registry.list_profiles()

    @staticmethod
    def _should_retry(exc: Exception) -> bool:
        """判断当前异常是否值得重试。"""

        if isinstance(exc, httpx.HTTPStatusError):
            status = exc.response.status_code
            return status in {408, 409, 429, 500, 502, 503, 504, 529}
        if isinstance(exc, (httpx.ConnectError, httpx.ReadTimeout, httpx.WriteTimeout, httpx.RemoteProtocolError)):
            return True
        return False

    async def chat(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        stream: bool = False,
        model: str | None = None,
    ) -> LLMResponse:
        """执行一次非流式聊天请求。"""

        profile = self.model_registry.get(model or self.model_alias)
        provider = self.provider_factory.create(profile)
        headers = provider.build_headers(profile)
        payload = provider.build_payload(profile, messages=messages, tools=tools, stream=stream)

        async with httpx.AsyncClient(timeout=self.timeout_seconds, follow_redirects=True) as client:
            last_exc: Exception | None = None
            for attempt in range(self.max_retries):
                try:
                    response = await client.post(
                        f"{profile.base_url.rstrip('/')}{profile.chat_path}",
                        headers=headers,
                        params=profile.query_params,
                        json=payload,
                    )
                    response.raise_for_status()
                    data = response.json()
                    break
                except Exception as exc:  # pragma: no cover - 网络抖动依赖真实环境
                    last_exc = exc
                    if attempt == self.max_retries - 1 or not self._should_retry(exc):
                        raise
                    await asyncio.sleep(1 + attempt)
            else:  # pragma: no cover
                raise last_exc or RuntimeError("LLM request failed")

        return provider.parse_response(profile, data)

    async def chat_stream(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        model: str | None = None,
    ):
        """执行一次流式聊天请求。"""

        profile = self.model_registry.get(model or self.model_alias)
        provider = self.provider_factory.create(profile)
        headers = provider.build_headers(profile)
        payload = provider.build_payload(profile, messages=messages, tools=tools, stream=True)

        async with httpx.AsyncClient(timeout=self.timeout_seconds, follow_redirects=True) as client:
            last_exc: Exception | None = None
            for attempt in range(self.max_retries):
                try:
                    async with client.stream(
                        "POST",
                        f"{profile.base_url.rstrip('/')}{profile.chat_path}",
                        headers=headers,
                        params=profile.query_params,
                        json=payload,
                    ) as response:
                        response.raise_for_status()
                        async for chunk in provider.parse_stream(profile, response):
                            yield chunk
                    return
                except Exception as exc:  # pragma: no cover - 网络抖动依赖真实环境
                    last_exc = exc
                    if attempt == self.max_retries - 1 or not self._should_retry(exc):
                        raise
                    await asyncio.sleep(1 + attempt)
            raise last_exc or RuntimeError("LLM stream request failed")
