"""工具注册表"""

from . import Tool


class ToolRegistry:
    """工具注册表，管理所有可用工具"""

    def __init__(self):
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        """注册工具"""
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool | None:
        """根据名称获取工具"""
        return self._tools.get(name)

    def list_tools(self) -> list[str]:
        """列出所有已注册工具的名称"""
        return list(self._tools.keys())

    def get_definitions(self) -> list[dict]:
        """返回 OpenAI function calling 格式的工具定义列表"""
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
        """
        执行工具

        Args:
            name: 工具名称
            arguments: 工具参数

        Returns:
            (result, error) 元组，error 为空表示执行成功
        """
        tool = self.get(name)
        if not tool:
            return "", f"工具 '{name}' 不存在"

        try:
            result = await tool.execute(**arguments)
            return str(result), ""
        except Exception as e:
            return "", str(e)
