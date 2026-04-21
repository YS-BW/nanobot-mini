"""OpenAI 兼容协议的 LLM 客户端。

第一阶段重构后，LLM 层只负责协议通信和结果解析：
 - 组装请求
 - 发 HTTP 请求
 - 解析标准响应

它不应该知道 session、tools 存储策略、CLI 展示方式这些上层概念。
"""

import json
from collections.abc import AsyncIterator

import httpx

from .errors import LLMResponseError
from .types import LLMResponse, LLMStreamChunk, ToolCall, ToolCallDelta


class LLMClient:
    """最小可用的聊天客户端。"""

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
    ):
        self.base_url = (base_url or "https://api.openai.com/v1").rstrip("/")
        self.api_key = api_key or ""
        self.model = model or "gpt-4o"

    async def chat(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        stream: bool = False,
    ) -> LLMResponse:
        """发送一次非流式聊天请求并解析返回。

        这里默认走 OpenAI 兼容的 `/chat/completions` 协议。
        """
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        payload = {"model": self.model, "messages": messages}
        if tools:
            payload["tools"] = tools
        if stream:
            payload["stream"] = True

        async with httpx.AsyncClient(timeout=120) as client:
            response = await client.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json=payload,
            )
            response.raise_for_status()
            data = response.json()

        try:
            choice = data["choices"][0]
            message = choice["message"]
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMResponseError("Invalid LLM response payload") from exc

        tool_calls: list[ToolCall] = []
        for index, tool_call in enumerate(message.get("tool_calls") or []):
            # 兼容部分提供方不返回 tool_call id 的情况。
            tool_id = tool_call.get("id") or f"tool_{index}_{tool_call['function']['name']}"
            tool_calls.append(
                ToolCall(
                    id=tool_id,
                    name=tool_call["function"]["name"],
                    arguments=json.loads(tool_call["function"]["arguments"]),
                )
            )

        return LLMResponse(
            content=message.get("content"),
            tool_calls=tool_calls,
            finish_reason=choice.get("finish_reason", "stop"),
        )

    async def chat_stream(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
    ) -> AsyncIterator[LLMStreamChunk]:
        """发送一次流式聊天请求，并解析成结构化增量。

        这里不再只返回纯文本，而是把文本增量和工具调用增量都保留下来，
        这样运行时主循环才能真正做到边吐字边收集 tool call。
        """
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        payload = {"model": self.model, "messages": messages, "stream": True}
        if tools:
            payload["tools"] = tools

        async with httpx.AsyncClient(timeout=120) as client:
            async with client.stream(
                "POST",
                f"{self.base_url}/chat/completions",
                headers=headers,
                json=payload,
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    if line == "data: [DONE]":
                        break
                    chunk = json.loads(line[6:])

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

                    reasoning_content = delta.get("reasoning_content") or ""
                    content = delta.get("content") or ""
                    finish_reason = choice.get("finish_reason")

                    if reasoning_content or content or tool_deltas or finish_reason is not None:
                        yield LLMStreamChunk(
                            reasoning_content=reasoning_content,
                            content=content,
                            tool_calls=tool_deltas,
                            finish_reason=finish_reason,
                        )
