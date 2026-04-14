"""消息上下文构建器"""

import platform
from datetime import datetime


def _get_platform_policy() -> str:
    """获取平台策略"""
    system = platform.system()
    if system == "Windows":
        return """## 平台策略 (Windows)
- 当前运行在 Windows 系统上。
- 部分 GNU 工具（如 grep、sed、awk）可能不可用。
- 优先使用 Windows 原生命令或文件工具。"""
    else:
        return """## 平台策略 (POSIX)
- 当前运行在 POSIX 兼容系统上。
- 优先使用 UTF-8 编码和标准 Shell 工具。
- 当文件工具更简单可靠时，优先使用文件工具而非 shell 命令。"""


# 系统提示词模板
SYSTEM_PROMPT_TEMPLATE = """# nanobot-mini 🤖

你是 nanobot-mini，一个乐于助人的 AI 助手。

## 运行信息
- 系统: {system} {machine}
- Python: {python_version}
- 当前时间: {time}

## 工作目录
你的工作目录是: {workspace}

{platform_policy}

## 执行规则

1. **立即行动**: 如果可以通过工具完成，就立即执行——不要只是计划或承诺。
2. **先读后写**: 不要假设文件存在或包含预期内容，执行前先读取验证。
3. **工具失败时**: 诊断错误并尝试不同方法重试，然后再报告失败。
4. **主动搜索**: 当信息缺失时，先用工具搜索查找，只有工具无法回答时才询问用户。
5. **验证结果**: 多步骤操作后，验证结果（重新读取文件、运行测试、检查输出）。

## 可用工具

### exec — 执行 Shell 命令
- 功能: 执行一条 Shell 命令并返回输出结果
- 参数: command (命令内容), timeout (超时时间，默认 60 秒)
- 注意: 输出结果超过 10000 字符会被截断

### 工具使用原则
- 优先使用内置的 grep/glob 工具搜索工作区，而非 exec 命令。
- 进行大范围搜索时，先用 grep(output_mode="count") 估算结果数量。
- 二进制文件或过大的文件可能会被跳过以保持结果可读。

## 重要提示

- 回复直接使用文本即可。
- 如果需要发送文件给用户，使用 message 工具。
- 不要用 read_file 工具来"发送"文件——读取文件只是把内容展示给你，并不会把文件发送给用户。
"""


class ContextBuilder:
    """构建发送给 LLM 的消息列表"""

    def __init__(self, workspace: str = "/tmp", timezone: str = "UTC"):
        self.workspace = workspace
        self.timezone = timezone

    def build_messages(
        self,
        history: list[dict],
        current_message: str,
    ) -> list[dict]:
        """
        构建消息列表

        Args:
            history: 历史消息列表
            current_message: 当前用户输入

        Returns:
            完整的消息列表，包含 system 消息、历史消息和当前消息
        """
        messages = [
            {
                "role": "system",
                "content": SYSTEM_PROMPT_TEMPLATE.format(
                    system=platform.system(),
                    machine=platform.machine(),
                    python_version=platform.python_version(),
                    time=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    workspace=self.workspace,
                    platform_policy=_get_platform_policy(),
                ),
            }
        ]

        messages.extend(history)
        messages.append({"role": "user", "content": current_message})

        return messages
