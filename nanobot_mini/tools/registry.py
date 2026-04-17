"""工具注册表。"""

from .base import Tool


class ToolRegistry:
    """管理所有已注册工具。"""

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

    def get_definitions(self) -> list[dict]:
        """返回 function calling 所需的工具定义。"""
        return [
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.parameters,
                },
            }
            for tool in self._tools.values()
        ]

    async def execute(self, name: str, arguments: dict) -> tuple[str, str]:
        """执行工具并返回 `(result, error)`。"""
        tool = self.get(name)
        if not tool:
            return "", f"工具 '{name}' 不存在"

        try:
            result = await tool.execute(**arguments)
            return str(result), ""
        except Exception as e:
            return "", str(e)
