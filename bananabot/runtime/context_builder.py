"""运行时上下文组装器。

上下文组装只关心“按什么顺序把哪些消息送给模型”，不关心消息如何持久化。
这样可以把存储逻辑和推理上下文逻辑拆开。
"""

from pathlib import Path

from .prompts import build_system_prompt


def build_context(session, workspace: Path) -> list[dict]:
    """按记忆、提示词、当前会话组装模型消息。

    当前顺序是：
    1. 长期记忆或摘要记忆
    2. system prompt
    3. 当前会话窗口
    """

    messages: list[dict] = []

    if session.has_memory():
        # 如果已经有长期记忆，就优先注入长期记忆，不再注入 summary。
        content = session.memory_path.read_text(encoding="utf-8")
        if content.strip():
            messages.append({"role": "system", "content": content})
    else:
        # 在没有长期记忆时，使用累计摘要帮助模型恢复历史上下文。
        summary_content = session.get_summary_text()
        if summary_content:
            messages.append({"role": "system", "content": summary_content})

    messages.append({"role": "system", "content": build_system_prompt(workspace)})
    messages.extend(session.messages)
    return messages
