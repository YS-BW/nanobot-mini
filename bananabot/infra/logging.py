"""调试日志辅助函数。

目前这里只保留最小可用的调试日志能力：把一次请求实际发送给模型的消息写入文件。
这样在出现上下文问题、compact 问题、提示词问题时，可以直接回看实际消息。
"""

import json


def write_debug_messages(session, messages: list[dict]) -> None:
    """把运行时消息写入调试文件。"""

    if not session.session_path:
        return

    debug_log = session.session_path.parent / "debug.json"
    debug_log.parent.mkdir(parents=True, exist_ok=True)
    simplified = [{"role": message.get("role"), "content": message.get("content")} for message in messages]
    with open(debug_log, "w", encoding="utf-8") as handle:
        json.dump(simplified, handle, ensure_ascii=False, indent=2)
