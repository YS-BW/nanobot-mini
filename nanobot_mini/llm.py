"""极简 LLM 调用，封装 OpenAI chat API"""
import os
import json
import httpx
from typing import AsyncIterator

from .types import LLMResponse, ToolCall


class LLM:
    def __init__(self, base_url: str | None = None, api_key: str | None = None, model: str = "gpt-4o"):
        self.base_url = (base_url or os.environ.get("BASE_URL", "https://api.openai.com/v1")).rstrip("/")
        self.api_key = api_key or os.environ.get("API_KEY", "") or ""
        self.model = model

    async def chat(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        stream: bool = False,
    ) -> LLMResponse:
        """单次 LLM 调用"""
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        payload = {
            "model": self.model,
            "messages": messages,
        }
        if tools:
            payload["tools"] = tools
        if stream:
            payload["stream"] = True

        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()

        choice = data["choices"][0]
        msg = choice["message"]

        tool_calls = []
        if msg.get("tool_calls"):
            for i, tc in enumerate(msg["tool_calls"]):
                tc_id = tc.get("id") or f"tool_{i}_{tc['function']['name']}"
                tool_calls.append(ToolCall(
                    id=tc_id,
                    name=tc["function"]["name"],
                    arguments=json.loads(tc["function"]["arguments"]),
                ))

        return LLMResponse(
            content=msg.get("content"),
            tool_calls=tool_calls,
            finish_reason=choice.get("finish_reason", "stop"),
        )

    async def chat_stream(
        self, messages: list[dict], tools: list[dict] | None = None
    ) -> AsyncIterator[str]:
        """流式调用，返回 content delta"""
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": True,
        }
        if tools:
            payload["tools"] = tools

        async with httpx.AsyncClient(timeout=120) as client:
            async with client.stream(
                "POST",
                f"{self.base_url}/chat/completions",
                headers=headers,
                json=payload,
            ) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if line.startswith("data: "):
                        if line == "data: [DONE]":
                            break
                        chunk = json.loads(line[6:])
                        delta = chunk["choices"][0]["delta"].get("content", "")
                        if delta:
                            yield delta
