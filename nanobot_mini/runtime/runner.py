"""运行时主循环，负责模型与工具交互。

这是项目里最接近“Agent 内核”的部分。
它不关心 CLI、session 文件、README，也不关心界面如何展示，
只关心这件事：

1. 把消息发给模型
2. 看模型是否要调工具
3. 如果要调，就执行工具并把结果塞回消息
4. 循环直到模型停止调用工具
"""

import json
from collections.abc import Callable

from ..llm import LLMClient, LLMResponse, ToolCall
from ..tools import ToolRegistry
from .events import RuntimeEvent


class AgentRunner:
    """执行核心的模型与工具循环。"""

    def __init__(self, llm: LLMClient, registry: ToolRegistry, max_iterations: int = 20):
        self.llm = llm
        self.registry = registry
        self.max_iterations = max_iterations

    async def run(
        self,
        messages: list[dict],
        event_callback: Callable[[RuntimeEvent], None] | None = None,
    ) -> LLMResponse:
        """执行运行时循环，直到模型不再调用工具。"""

        iteration = 0

        def emit(event_type: str, message: str | None = None, data: dict | None = None) -> None:
            """向上层发送运行时事件。"""
            if event_callback:
                event_callback(RuntimeEvent(type=event_type, message=message, data=data))

        while iteration < self.max_iterations:
            iteration += 1
            emit("assistant_thinking", f"thinking... round {iteration}")

            content_parts: list[str] = []
            finish_reason = "stop"
            tool_call_buffers: dict[int, dict] = {}

            async for chunk in self.llm.chat_stream(
                messages=messages,
                tools=self.registry.get_definitions() if self.registry.list_tools() else None,
            ):
                if chunk.reasoning_content:
                    emit(
                        "assistant_reasoning_delta",
                        chunk.reasoning_content,
                        data={"delta": chunk.reasoning_content},
                    )

                if chunk.content:
                    content_parts.append(chunk.content)
                    emit("assistant_delta", chunk.content, data={"delta": chunk.content})

                for tool_delta in chunk.tool_calls:
                    buffer = tool_call_buffers.setdefault(
                        tool_delta.index,
                        {"id": None, "name": None, "arguments_parts": []},
                    )
                    if tool_delta.id:
                        buffer["id"] = tool_delta.id
                    if tool_delta.name:
                        buffer["name"] = tool_delta.name
                    if tool_delta.arguments_chunk:
                        buffer["arguments_parts"].append(tool_delta.arguments_chunk)

                if chunk.finish_reason:
                    finish_reason = chunk.finish_reason

            response = LLMResponse(
                content="".join(content_parts) or None,
                tool_calls=self._build_tool_calls(tool_call_buffers),
                finish_reason=finish_reason,
            )

            # assistant 消息会先写入运行时消息列表，之后再由应用层决定是否持久化。
            assistant_msg: dict = {
                "role": "assistant",
                "content": response.content or "",
            }
            if response.tool_calls:
                assistant_msg["tool_calls"] = [
                    {
                        "id": tool_call.id,
                        "function": {
                            "name": tool_call.name,
                            "arguments": json.dumps(tool_call.arguments),
                        },
                    }
                    for tool_call in response.tool_calls
                ]
            messages.append(assistant_msg)

            if not response.tool_calls:
                return response

            for tool_call in response.tool_calls:
                # 这里把工具调用参数转成字符串，只用于日志展示，不影响真实执行。
                args_str = ", ".join(
                    f"{key}={repr(value)[:50]}" for key, value in tool_call.arguments.items()
                )
                emit(
                    "tool_call_started",
                    f"tool  {tool_call.name}({args_str})",
                    data={"tool_name": tool_call.name, "arguments": tool_call.arguments},
                )

                result, error = await self.registry.execute(tool_call.name, tool_call.arguments)
                if error:
                    emit("error", f"error: {error}", data={"tool_name": tool_call.name})
                    result = f"[错误] {error}"

                # 进度展示只显示截断后的结果，真正的 tool 消息仍然保留完整输出。
                display_result = result[:500] + "..." if len(result) > 500 else result
                emit(
                    "tool_call_finished",
                    f"result  {display_result}",
                    data={"tool_name": tool_call.name},
                )
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": result,
                    }
                )

        return LLMResponse(content="[已达到最大迭代次数]")

    def _build_tool_calls(self, tool_call_buffers: dict[int, dict]) -> list[ToolCall]:
        """把流式工具调用片段还原成完整结构。

        OpenAI 兼容 stream 协议会把 arguments 拆成很多片段。
        这里统一按 index 聚合，最后再解析成 dict，避免上层反复写一遍拼装逻辑。
        """

        tool_calls: list[ToolCall] = []
        for index in sorted(tool_call_buffers):
            buffer = tool_call_buffers[index]
            name = buffer["name"]
            if not name:
                raise ValueError(f"Missing tool name for streamed tool call #{index}")

            arguments_text = "".join(buffer["arguments_parts"]).strip()
            if not arguments_text:
                arguments = {}
            else:
                try:
                    arguments = json.loads(arguments_text)
                except json.JSONDecodeError as exc:
                    raise ValueError(
                        f"Invalid streamed tool arguments for {name}: {arguments_text}"
                    ) from exc

            tool_calls.append(
                ToolCall(
                    id=buffer["id"] or f"tool_{index}_{name}",
                    name=name,
                    arguments=arguments,
                )
            )
        return tool_calls
