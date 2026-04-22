"""工具注册表。"""

from .base import Tool
from .specs import ToolSpec


class ToolRegistry:
    """管理已注册工具。"""

    def __init__(self):
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        """注册工具。"""
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool | None:
        """按名称获取工具。"""
        return self._tools.get(name)

    def list_tools(self) -> list[str]:
        """列出所有工具名称。"""
        return list(self._tools.keys())

    def get_spec(self, name: str) -> ToolSpec | None:
        """按名称获取工具标准描述。"""
        tool = self.get(name)
        return tool.spec if tool else None

    def list_specs(self) -> list[ToolSpec]:
        """列出所有工具标准描述。"""
        return [tool.spec for tool in self._tools.values()]

    def get_definitions(self) -> list[dict]:
        """返回 function calling 所需的工具定义。"""
        return [tool.definition() for tool in self._tools.values()]

    async def execute(self, name: str, arguments: dict) -> tuple[str, str]:
        """执行工具并返回 `(result, error)`。"""

        tool = self.get(name)
        if not tool:
            return "", f"工具 '{name}' 不存在"

        try:
            return str(await tool.execute(**arguments)), ""
        except Exception as exc:
            return "", str(exc)
