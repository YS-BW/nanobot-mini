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
from typing import Any

from ..llm import LLMClient, LLMResponse, ToolCall
from ..tools import ToolRegistry
from .coordinator import RuntimeCoordinator
from .events import EventEnvelope
from .models import StepKind


class AgentRunner:
    """执行核心的模型与工具循环。"""

    def __init__(self, llm: LLMClient, registry: ToolRegistry, max_iterations: int = 20):
        self.llm = llm
        self.registry = registry
        self.max_iterations = max_iterations

    def _tools_enabled(self) -> bool:
        """判断当前模型是否声明支持工具调用。"""

        if not hasattr(self.llm, "get_current_profile"):
            return True
        profile = self.llm.get_current_profile()
        return profile.capabilities.supports_tools

    async def run(
        self,
        messages: list[dict],
        event_callback: Callable[[EventEnvelope], None] | None = None,
        *,
        thread_id: str | None = None,
        task_run_id: str | None = None,
        thread_title: str | None = None,
        thread_metadata: dict[str, Any] | None = None,
        task_metadata: dict[str, Any] | None = None,
        state_store=None,
    ) -> LLMResponse:
        """执行运行时循环，直到模型不再调用工具。"""

        iteration = 0
        runtime_task_metadata = dict(task_metadata or {})
        runtime_task_metadata.setdefault("max_iterations", self.max_iterations)
        coordinator = RuntimeCoordinator.from_messages(
            messages,
            event_callback=event_callback,
            thread_id=thread_id,
            task_run_id=task_run_id,
            thread_title=thread_title,
            thread_metadata=thread_metadata,
            task_metadata=runtime_task_metadata,
            state_store=state_store,
        )
        coordinator.start_task_run(metadata={"message_count": len(messages)})

        current_turn = None
        try:
            while iteration < self.max_iterations:
                iteration += 1
                current_turn = coordinator.start_turn(payload={"iteration": iteration})
                reasoning_step = coordinator.start_step(
                    current_turn,
                    StepKind.REASONING,
                    event_type="assistant_thinking",
                    message=f"thinking... round {iteration}",
                    payload={"iteration": iteration},
                )

                content_parts: list[str] = []
                reasoning_parts: list[str] = []
                finish_reason = "stop"
                tool_call_buffers: dict[int, dict] = {}
                assistant_step = None

                async for chunk in self.llm.chat_stream(
                    messages=messages,
                    tools=(
                        self.registry.get_definitions()
                        if self.registry.list_tools() and self._tools_enabled()
                        else None
                    ),
                ):
                    if chunk.reasoning_content:
                        reasoning_parts.append(chunk.reasoning_content)
                        coordinator.emit_event(
                            "assistant_reasoning_delta",
                            message=chunk.reasoning_content,
                            turn=current_turn,
                            step=reasoning_step,
                            payload={
                                "delta": chunk.reasoning_content,
                                "iteration": iteration,
                            },
                        )

                    if chunk.content:
                        if assistant_step is None:
                            assistant_step = coordinator.start_step(
                                current_turn,
                                StepKind.ASSISTANT_MESSAGE,
                                event_type="assistant_message_started",
                                payload={"iteration": iteration},
                            )
                        content_parts.append(chunk.content)
                        coordinator.emit_event(
                            "assistant_delta",
                            message=chunk.content,
                            turn=current_turn,
                            step=assistant_step,
                            payload={"delta": chunk.content, "iteration": iteration},
                        )

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
                    reasoning_content="".join(reasoning_parts) or None,
                )
                coordinator.complete_step(
                    reasoning_step,
                    event_type="reasoning_completed",
                    payload={
                        "iteration": iteration,
                        "reasoning_chars": len(response.reasoning_content or ""),
                    },
                )

                # assistant 消息会先写入运行时消息列表，之后再由应用层决定是否持久化。
                assistant_msg: dict = response.assistant_message or {
                    "role": "assistant",
                    "content": response.content or "",
                }
                if response.reasoning_content:
                    assistant_msg.setdefault("reasoning_content", response.reasoning_content)
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

                if response.tool_calls:
                    request_step = coordinator.start_step(
                        current_turn,
                        StepKind.TOOL_CALL_REQUESTED,
                        event_type="tool_call_requested",
                        payload={
                            "iteration": iteration,
                            "tool_calls": [
                                {"id": call.id, "name": call.name} for call in response.tool_calls
                            ],
                        },
                    )
                    coordinator.complete_step(
                        request_step,
                        event_type="tool_call_request_recorded",
                        payload={
                            "iteration": iteration,
                            "tool_call_count": len(response.tool_calls),
                        },
                    )
                    if assistant_step is not None:
                        coordinator.complete_step(
                            assistant_step,
                            event_type="assistant_message_buffered",
                            message=response.content,
                            payload={
                                "iteration": iteration,
                                "content": response.content or "",
                                "finish_reason": response.finish_reason,
                            },
                        )

                if not response.tool_calls:
                    if assistant_step is None:
                        assistant_step = coordinator.start_step(
                            current_turn,
                            StepKind.ASSISTANT_MESSAGE,
                            event_type="assistant_message_started",
                            payload={"iteration": iteration},
                        )
                    coordinator.complete_step(
                        assistant_step,
                        event_type="assistant_message",
                        message=response.content or "[无回复内容]",
                        payload={
                            "iteration": iteration,
                            "content": response.content or "",
                            "finish_reason": response.finish_reason,
                        },
                    )
                    coordinator.complete_turn(
                        current_turn,
                        payload={
                            "iteration": iteration,
                            "finish_reason": response.finish_reason,
                        },
                    )
                    coordinator.complete_task_run(
                        payload={
                            "iterations": iteration,
                            "finish_reason": response.finish_reason,
                        }
                    )
                    return response

                for tool_call in response.tool_calls:
                    # 这里把工具调用参数转成字符串，只用于日志展示，不影响真实执行。
                    args_str = ", ".join(
                        f"{key}={repr(value)[:50]}" for key, value in tool_call.arguments.items()
                    )
                    started_step = coordinator.start_step(
                        current_turn,
                        StepKind.TOOL_CALL_STARTED,
                        event_type="tool_call_started",
                        message=f"tool  {tool_call.name}({args_str})",
                        payload={
                            "tool_name": tool_call.name,
                            "arguments": tool_call.arguments,
                            "iteration": iteration,
                        },
                    )

                    result, error = await self.registry.execute(tool_call.name, tool_call.arguments)
                    if error:
                        coordinator.fail_step(
                            started_step,
                            error=error,
                            message=f"error: {error}",
                            payload={
                                "tool_name": tool_call.name,
                                "arguments": tool_call.arguments,
                            },
                        )
                        coordinator.emit_event(
                            "error",
                            status="failed",
                            message=f"error: {error}",
                            turn=current_turn,
                            step=started_step,
                            payload={"tool_name": tool_call.name, "arguments": tool_call.arguments},
                        )
                        result = f"[错误] {error}"
                    else:
                        coordinator.complete_step(
                            started_step,
                            event_type="tool_call_start_completed",
                            payload={
                                "tool_name": tool_call.name,
                                "arguments": tool_call.arguments,
                            },
                        )

                    # 进度展示只显示截断后的结果，真正的 tool 消息仍然保留完整输出。
                    display_result = result[:500] + "..." if len(result) > 500 else result
                    finished_step = coordinator.start_step(
                        current_turn,
                        StepKind.TOOL_CALL_FINISHED,
                        event_type="tool_call_finished",
                        message=f"result  {display_result}",
                        payload={
                            "tool_name": tool_call.name,
                            "iteration": iteration,
                        },
                    )
                    coordinator.complete_step(
                        finished_step,
                        event_type="tool_call_recorded",
                        payload={
                            "tool_name": tool_call.name,
                            "result_preview": display_result,
                            "result_length": len(result),
                        },
                    )
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "content": result,
                        }
                    )

                coordinator.complete_turn(
                    current_turn,
                    payload={
                        "iteration": iteration,
                        "tool_call_count": len(response.tool_calls),
                        "finish_reason": response.finish_reason,
                    },
                )
                current_turn = None
        except Exception as exc:
            if current_turn is not None:
                coordinator.fail_turn(current_turn, str(exc), payload={"iteration": iteration})
            coordinator.fail_task_run(str(exc), payload={"iteration": iteration})
            raise

        response = LLMResponse(content="[已达到最大迭代次数]", finish_reason="max_iterations")
        coordinator.complete_task_run(
            payload={
                "iterations": iteration,
                "finish_reason": response.finish_reason,
            }
        )
        return response

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
