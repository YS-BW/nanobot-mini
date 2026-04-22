"""TUI 渲染辅助函数。

这里只放纯文本格式化逻辑，不碰 Textual 组件和应用状态。
"""

from __future__ import annotations

from datetime import datetime
from textwrap import wrap


def one_line(text: str | None, limit: int = 44) -> str:
    """把多行文本压成单行预览，并做长度截断。"""

    if not text:
        return ""
    compact = " ".join(part.strip() for part in text.splitlines() if part.strip())
    if len(compact) <= limit:
        return compact
    return f"{compact[: limit - 1]}…"


def status_lines(status: dict) -> list[str]:
    """把 thread 状态格式化成多行文本。"""

    return [
        f"当前线程: {status['thread_id']}",
        f"消息数量: {status['message_count']}",
        f"工作目录: {status['workspace']}",
        f"模型: {status.get('model_alias', status['model'])} -> {status['model']}",
        f"window(session.jsonl): {status['paths']['window']}",
        f"history: {status['paths']['history']}",
        f"summary: {status['paths']['summary']}",
        f"memory: {status['paths']['memory']}",
        f"history 条目: {status['history_count']}",
        f"summary 条目: {status['summary_count']}",
        f"memory: {'存在' if status['has_memory'] else '无'}",
    ]


def banana_lines(info: dict) -> list[str]:
    """把 BANANA 指令文件信息格式化成多行文本。"""

    lines = [f"全局指令: {info['global_path']}"]
    if info["global_preview"]:
        lines.extend(info["global_preview"].splitlines())
    else:
        lines.append("暂无全局指令")

    lines.append("")
    lines.append(f"项目指令: {info['project_path'] or '无'}")
    if info["project_preview"]:
        lines.extend(info["project_preview"].splitlines())
    else:
        lines.append("暂无项目指令")

    lines.extend(
        [
            "",
            "用法:",
            "  ~/.bananabot/BANANA.md      全局指令",
            "  <project>/BANANA.md         项目指令",
        ]
    )
    return lines


def render_prefixed_block(prefix: str, text: str) -> str:
    """把文本渲染成终端式块。"""

    stripped = (text or "").strip()
    if not stripped:
        return prefix
    lines = stripped.splitlines()
    return "\n".join([f"{prefix} {lines[0]}"] + [f"  {line}" for line in lines[1:]])


def picker_line(primary: str, secondary: str, limit: int = 72, gap: int = 2) -> str:
    """把列表项压成单行双列，便于做紧凑展示。"""

    left = primary.strip()
    right = secondary.strip()
    if not right:
        return one_line(left, limit=limit)

    raw = f"{left}{' ' * gap}{right}"
    if len(raw) <= limit:
        return raw

    max_right = max(12, limit - len(left) - gap)
    return f"{left}{' ' * gap}{one_line(right, limit=max_right)}"


def format_bytes(size: int) -> str:
    """把字节数转成可读体积。"""

    units = ["B", "KB", "MB", "GB"]
    value = float(size)
    for unit in units:
        if value < 1024 or unit == units[-1]:
            return f"{value:.1f}{unit}" if unit != "B" else f"{int(value)}B"
        value /= 1024
    return f"{int(size)}B"


def format_relative_time(timestamp: float) -> str:
    """把时间戳转成简短相对时间。"""

    delta = max(0, int(datetime.now().timestamp() - timestamp))
    if delta < 60:
        return "just now"
    if delta < 3600:
        return f"{delta // 60} min ago"
    if delta < 86400:
        return f"{delta // 3600} hours ago"
    if delta < 86400 * 7:
        return f"{delta // 86400} days ago"
    return f"{delta // (86400 * 7)} weeks ago"


def wrap_for_box(text: str, width: int = 66) -> list[str]:
    """把 thinking 文本按固定宽度切成多行。"""

    lines: list[str] = []
    for raw_line in text.splitlines() or ([text] if text else []):
        lines.extend(wrap(raw_line, width=width) or [""])
    return lines or ["thinking..."]


def render_thinking_box(
    title: str,
    lines: list[str],
    max_height: int = 5,
    width: int = 66,
    min_height: int = 0,
) -> str:
    """渲染一个带高度约束的 thinking 框。"""

    target_height = max(min_height, min(max_height, len(lines)))
    visible = [line[:width].ljust(width) for line in lines[-target_height:]]
    while len(visible) < target_height:
        visible.insert(0, " " * width)
    top = f"┌ {title} " + "─" * max(8, width - len(title) - 1)
    body = [f"│ {line}" for line in visible]
    bottom = "└" + "─" * (width + 1)
    return "\n".join([top] + body + [bottom])
