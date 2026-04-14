"""数据类型定义"""
from dataclasses import dataclass, field
from typing import Any

@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict

@dataclass
class LLMResponse:
    content: str | None
    tool_calls: list[ToolCall] = field(default_factory=list)
    finish_reason: str = "stop"

@dataclass
class ToolResult:
    tool_call_id: str
    name: str
    content: str
