"""极简工具系统"""
import asyncio
from abc import ABC, abstractmethod
from typing import Any


class Tool(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        ...

    @property
    @abstractmethod
    def description(self) -> str:
        ...

    @property
    @abstractmethod
    def parameters(self) -> dict:
        ...

    @abstractmethod
    async def execute(self, **kwargs) -> str:
        ...


class ToolRegistry:
    def __init__(self):
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool):
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def get_definitions(self) -> list[dict]:
        """返回 OpenAI function calling 格式"""
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
        """执行工具，返回 (result, error)"""
        tool = self.get(name)
        if not tool:
            return "", f"Tool '{name}' not found"
        try:
            result = await tool.execute(**arguments)
            return str(result), ""
        except Exception as e:
            return "", str(e)


class ExecTool(Tool):
    """执行 shell 命令的工具"""

    name = "exec"
    description = "Execute a shell command and return the output"

    parameters = {
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": "The shell command to execute",
            },
            "timeout": {
                "type": "integer",
                "description": "Timeout in seconds (default 60)",
                "default": 60,
            },
        },
        "required": ["command"],
    }

    def __init__(self, working_dir: str = "/tmp"):
        self.working_dir = working_dir

    async def execute(self, command: str, timeout: int = 60, **_) -> str:
        proc = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=self.working_dir,
        )
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
            output = stdout.decode() + stderr.decode()
            return output + f"\n[Exit code: {proc.returncode}]"
        except asyncio.TimeoutError:
            proc.kill()
            return f"[Timeout after {timeout}s]"
