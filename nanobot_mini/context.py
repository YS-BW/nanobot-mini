"""上下文构建器"""

import platform
from datetime import datetime
from pathlib import Path


def build_context(session) -> list[dict]:
    """
    构建发送给 LLM 的 messages 列表

    顺序：memory/summary → system prompt → session.messages

    Args:
        session: Session 实例

    Returns:
        完整的消息列表
    """
    messages = []

    # 1. Memory 或 Summary 作为独立的 system 消息（互斥）
    if session.has_memory():
        content = session.memory_path.read_text(encoding="utf-8")
        if content.strip():
            messages.append({"role": "system", "content": content})
    else:
        summary_content = session.get_summary_text()
        if summary_content:
            messages.append({"role": "system", "content": summary_content})

    # 2. 系统提示词
    system_prompt = build_system_prompt()
    messages.append({"role": "system", "content": system_prompt})

    # 3. 拼接 session.messages
    messages.extend(session.messages)

    return messages


def build_system_prompt() -> str:
    """构建系统提示词"""
    system_info = """# 🍌 BananaBot

你是 BananaBot，杠精+梗王。默认别人说的不对，第一反应是反驳。

## 表达
- 强口语化 + 梗（典中典/绷不住了/给我整不会了/离谱）
- 短句，反问句多，节奏快
- 轻口脏话：卧槽/我靠/我真服了/离谱

## 示例
"卧槽，你这就绷不住了？前提都没了你在这推结果？典中典。"
"不是，你先把概念搞明白行不行？越说越离谱。"
"我靠，你这是自证循环搁这套娃呢？还能被你说成分析，笑死。"

## 工具
exec: 执行 Shell 命令，参数 command / timeout

## 运行信息
- 系统: {system} {machine}
- Python: {python_version}
- 当前时间: {time}
- 工作目录: {workspace}

{platform_policy}
"""
    return system_info.format(
        system=platform.system(),
        machine=platform.machine(),
        python_version=platform.python_version(),
        time=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        workspace=Path.cwd(),
        platform_policy=_get_platform_policy(),
    )


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
