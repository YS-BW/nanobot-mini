"""极简 ContextBuilder — 自己写"""
from datetime import datetime

SYSTEM_PROMPT = """You are a helpful AI assistant.

You have access to tools. When a user asks you to do something:
1. If you need to run a command, use the exec tool
2. If you're not sure how to do something, try it and see

Current time: {time}
Working directory: {workspace}
"""


class ContextBuilder:
    def __init__(self, workspace: str = "/tmp", timezone: str = "UTC"):
        self.workspace = workspace
        self.timezone = timezone

    def build_messages(self, history: list[dict], current_message: str) -> list[dict]:
        """构建发送给 LLM 的消息列表"""
        messages = []

        # System prompt
        messages.append(
            {
                "role": "system",
                "content": SYSTEM_PROMPT.format(
                    time=datetime.now().strftime("%Y-%m-%d %H:%M"),
                    workspace=self.workspace,
                ),
            }
        )

        # History
        messages.extend(history)

        # Current message
        messages.append({"role": "user", "content": current_message})

        return messages
