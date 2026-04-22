"""受控的 OpenAI-compatible provider。"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from copy import deepcopy

import httpx

from ..errors import LLMResponseError
from ..registry import ModelProfile
from ..types import LLMResponse, LLMStreamChunk, ToolCall, ToolCallDelta


class OpenAICompatProvider:
    """兼容当前白名单内 `/chat/completions` 风格 provider。"""

    def normalize_messages(self, messages: list[dict]) -> list[dict]:
        """把历史消息裁剪到更稳定的兼容结构。"""

        normalized: list[dict] = []
        for raw_message in messages:
            role = raw_message.get("role")
            if role not in {"system", "user", "assistant", "tool"}:
                continue

            message: dict = {"role": role}
            if role in {"system", "user", "assistant"}:
                message["content"] = raw_message.get("content", "")
            elif role == "tool":
                message["content"] = raw_message.get("content", "")
                if raw_message.get("tool_call_id"):
                    message["tool_call_id"] = raw_message["tool_call_id"]

            if role == "assistant" and raw_message.get("tool_calls"):
                message["tool_calls"] = raw_message["tool_calls"]

            normalized.append(message)
        return normalized

    def build_headers(self, profile: ModelProfile) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if profile.api_key:
            headers["Authorization"] = f"Bearer {profile.api_key}"
        headers.update(profile.headers)
        return headers

    def build_payload(
        self,
        profile: ModelProfile,
        messages: list[dict],
        tools: list[dict] | None,
        stream: bool,
    ) -> dict:
        payload = {
            "model": profile.model,
            "messages": self.normalize_messages(messages),
            "stream": stream,
        }
        if tools and profile.capabilities.supports_tools:
            payload["tools"] = tools
        payload.update(deepcopy(profile.extra_body))
        return payload

    def parse_response(self, profile: ModelProfile, data: dict) -> LLMResponse:
        try:
            choice = data["choices"][0]
            message = dict(choice["message"])
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMResponseError("Invalid LLM response payload") from exc

        content, reasoning_content = self._extract_message_parts(message)
        tool_calls = self._build_tool_calls(message.get("tool_calls") or [])
        assistant_message = dict(message)
        assistant_message.setdefault("role", "assistant")
        assistant_message["content"] = assistant_message.get("content") if assistant_message.get("content") is not None else content

        return LLMResponse(
            content=content,
            tool_calls=tool_calls,
            finish_reason=choice.get("finish_reason", "stop"),
            reasoning_content=reasoning_content,
            assistant_message=assistant_message,
        )

    async def parse_stream(
        self,
        profile: ModelProfile,
        response: httpx.Response,
    ) -> AsyncIterator[LLMStreamChunk]:
        async for line in response.aiter_lines():
            if not line or line.startswith(":"):
                continue
            if not line.startswith("data: "):
                continue
            if line == "data: [DONE]":
                break

            chunk = json.loads(line[6:])
            if not chunk.get("choices"):
                continue
            try:
                choice = chunk["choices"][0]
                delta = choice.get("delta") or {}
            except (KeyError, IndexError, TypeError) as exc:
                raise LLMResponseError("Invalid LLM stream payload") from exc

            tool_deltas: list[ToolCallDelta] = []
            for tool_call in delta.get("tool_calls") or []:
                function = tool_call.get("function") or {}
                tool_deltas.append(
                    ToolCallDelta(
                        index=tool_call.get("index", 0),
                        id=tool_call.get("id"),
                        name=function.get("name"),
                        arguments_chunk=function.get("arguments", ""),
                    )
                )

            reasoning_content = self._extract_delta_reasoning(delta)
            content = delta.get("content") or ""
            finish_reason = choice.get("finish_reason")

            if reasoning_content or content or tool_deltas or finish_reason is not None:
                yield LLMStreamChunk(
                    reasoning_content=reasoning_content,
                    content=content,
                    tool_calls=tool_deltas,
                    finish_reason=finish_reason,
                )

    def _extract_delta_reasoning(self, delta: dict) -> str:
        reasoning = delta.get("reasoning_content") or ""
        if reasoning:
            return reasoning
        details = delta.get("reasoning_details") or []
        parts: list[str] = []
        for item in details:
            text = item.get("text") if isinstance(item, dict) else None
            if text:
                parts.append(text)
        return "".join(parts)

    def _extract_message_parts(self, message: dict) -> tuple[str | None, str | None]:
        content = message.get("content")
        reasoning = message.get("reasoning_content")
        if not reasoning:
            details = message.get("reasoning_details") or []
            parts: list[str] = []
            for item in details:
                text = item.get("text") if isinstance(item, dict) else None
                if text:
                    parts.append(text)
            reasoning = "".join(parts) or None
        if isinstance(content, str) and "<think>" in content and "</think>" in content:
            start = content.find("<think>")
            end = content.find("</think>")
            if start != -1 and end != -1 and end > start:
                think_text = content[start + 7 : end].strip()
                if think_text and not reasoning:
                    reasoning = think_text
                content = (content[:start] + content[end + 8 :]).strip() or None
        return content, reasoning

    def _build_tool_calls(self, raw_tool_calls: list[dict]) -> list[ToolCall]:
        tool_calls: list[ToolCall] = []
        for index, tool_call in enumerate(raw_tool_calls):
            function = tool_call.get("function") or {}
            arguments_text = function.get("arguments") or "{}"
            try:
                arguments = json.loads(arguments_text) if isinstance(arguments_text, str) else arguments_text
            except json.JSONDecodeError as exc:
                raise LLMResponseError(f"Invalid tool arguments: {arguments_text}") from exc
            tool_id = tool_call.get("id") or f"tool_{index}_{function.get('name', 'unknown')}"
            tool_calls.append(
                ToolCall(
                    id=tool_id,
                    name=function.get("name") or "unknown",
                    arguments=arguments or {},
                )
            )
        return tool_calls
