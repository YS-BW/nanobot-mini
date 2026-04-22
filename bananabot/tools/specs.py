"""工具静态描述。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(slots=True, frozen=True)
class ToolSpec:
    """工具的静态描述信息。"""

    name: str
    description: str
    parameters: dict[str, Any]

    def to_definition(self) -> dict[str, Any]:
        """转换成模型工具调用定义。"""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }
