"""DashScope provider。"""

from __future__ import annotations

from copy import deepcopy

from ..registry import ModelProfile
from .openai_compat import OpenAICompatProvider


class DashScopeProvider(OpenAICompatProvider):
    """补齐 DashScope thinking 参数组织。"""

    def build_payload(self, profile: ModelProfile, messages: list[dict], tools: list[dict] | None, stream: bool) -> dict:
        payload = super().build_payload(profile, messages, tools, stream)
        parameters = deepcopy(payload.pop("parameters", {}))
        for key in ("enable_thinking", "preserve_thinking", "thinking_budget"):
            if key in payload:
                parameters[key] = payload.pop(key)
        if parameters:
            payload["parameters"] = parameters
        return payload
