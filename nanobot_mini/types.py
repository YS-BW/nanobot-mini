"""数据类型定义"""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ToolCall:
    """LLM 调用的工具"""
    id: str
    name: str
    arguments: dict


@dataclass
class LLMResponse:
    """LLM 响应"""
    content: str | None
    tool_calls: list[ToolCall] = field(default_factory=list)
    finish_reason: str = "stop"


@dataclass
class ToolResult:
    """工具执行结果"""
    tool_call_id: str
    name: str
    content: str
