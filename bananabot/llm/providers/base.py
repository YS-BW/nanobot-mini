"""Provider 抽象接口。"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Protocol

import httpx

from ..registry import ModelProfile
from ..types import LLMResponse, LLMStreamChunk


class BaseProvider(Protocol):
    """定义 provider 最小接口。"""

    def build_headers(self, profile: ModelProfile) -> dict[str, str]: ...

    def build_payload(
        self,
        profile: ModelProfile,
        messages: list[dict],
        tools: list[dict] | None,
        stream: bool,
    ) -> dict: ...

    def parse_response(self, profile: ModelProfile, data: dict) -> LLMResponse: ...

    def parse_stream(
        self,
        profile: ModelProfile,
        response: httpx.Response,
    ) -> AsyncIterator[LLMStreamChunk]: ...
