"""Agent 运行器 - 核心 LLM ↔ 工具循环"""

import json
from typing import Callable

from .llm import LLM
from .tools import ToolRegistry
from .types import LLMResponse


class AgentRunner:
    """Agent 运行器，执行 LLM 与工具的循环交互"""

    def __init__(
        self,
        llm: LLM,
        registry: ToolRegistry,
        max_iterations: int = 20,
    ):
        self.llm = llm
        self.registry = registry
        self.max_iterations = max_iterations

    async def run(
        self,
        messages: list[dict],
        progress_callback: Callable[[str], None] | None = None,
    ) -> LLMResponse:
        """
        执行 Agent 循环

        Args:
            messages: 初始消息列表（包含 system prompt）
            progress_callback: 进度回调，用于显示中间过程

        Returns:
            最终 LLM 响应
        """
        iteration = 0

        def _progress(msg: str):
            if progress_callback:
                progress_callback(msg)

        while iteration < self.max_iterations:
            iteration += 1

            # 调用 LLM
            _progress(f"[yellow]🍌 思考中... (第 {iteration} 轮)[/yellow]")
            response = await self.llm.chat(
                messages=messages,
                tools=(
                    self.registry.get_definitions()
                    if self.registry._tools
                    else None
                ),
            )

            # 构建 assistant 消息
            assistant_msg: dict = {
                "role": "assistant",
                "content": response.content or "",
            }
            if response.tool_calls:
                assistant_msg["tool_calls"] = [
                    {
                        "id": tc.id,
                        "function": {
                            "name": tc.name,
                            "arguments": json.dumps(tc.arguments),
                        },
                    }
                    for tc in response.tool_calls
                ]
            messages.append(assistant_msg)

            # 如果没有 tool_calls，直接返回
            if not response.tool_calls:
                return response

            # 执行工具
            for tc in response.tool_calls:
                args_str = ", ".join(
                    f"{k}={repr(v)[:50]}" for k, v in tc.arguments.items()
                )
                _progress(f"[yellow]⚡ 调用工具:[/yellow] [green]{tc.name}[/green]({args_str})")

                result, error = await self.registry.execute(tc.name, tc.arguments)
                if error:
                    _progress(f"[red]✗ 错误: {error}[/red]")
                    result = f"[错误] {error}"

                # 截断过长输出
                display_result = result[:500] + "..." if len(result) > 500 else result
                _progress(f"[dim]└ 结果:[/dim] {display_result}[/dim]")

                tool_msg = {
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": result,
                }
                messages.append(tool_msg)

        # 达到最大迭代次数
        return LLMResponse(content="[已达到最大迭代次数]")
