"""Shell 执行工具。"""

import asyncio

from .base import Tool
from .specs import ToolSpec


class ExecTool(Tool):
    """执行 Shell 命令并返回结果。"""

    name = "exec"
    description = "执行一条 Shell 命令并返回输出结果"

    parameters = {
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": "要执行的 Shell 命令",
            },
            "timeout": {
                "type": "integer",
                "description": "超时时间（秒），默认 60",
                "default": 60,
            },
        },
        "required": ["command"],
    }

    def __init__(self, working_dir: str = "/tmp"):
        self.working_dir = working_dir

    @property
    def spec(self) -> ToolSpec:
        """返回 shell 工具描述。"""
        return ToolSpec(
            name=self.name,
            description=self.description,
            parameters=self.parameters,
        )

    async def execute(self, command: str, timeout: int = 60, **_) -> str:
        """执行 Shell 命令。"""
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
            await proc.wait()
            return f"[命令执行超时，已在 {timeout} 秒后被终止]"
