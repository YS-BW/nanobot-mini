"""TUI 列表项和候选数据构建。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from textual.widgets import ListItem, Static

from .cli_render import format_bytes, format_relative_time, one_line, picker_line


@dataclass
class ThreadEntry:
    """线程选择器里展示的一条摘要。"""

    thread_id: str
    title: str
    subtitle: str
    sort_key: float


class ThreadListItem(ListItem):
    """线程选择器中的单条可选项。"""

    def __init__(self, entry: ThreadEntry):
        self.entry = entry
        summary = picker_line(entry.thread_id, entry.title, limit=68)
        super().__init__(
            Static(summary, classes="picker-item-text"),
            classes="picker-item",
        )


@dataclass(frozen=True)
class CommandEntry:
    """命令候选列表里的一条命令定义。"""

    command: str
    description: str


class CommandListItem(ListItem):
    """命令候选列表中的单条可选项。"""

    def __init__(self, entry: CommandEntry):
        self.entry = entry
        summary = picker_line(entry.command, entry.description, limit=68)
        super().__init__(
            Static(summary, classes="picker-item-text"),
            classes="picker-item",
        )


@dataclass(frozen=True)
class ModelEntry:
    """模型候选列表中的一条定义。"""

    alias: str
    title: str
    subtitle: str
    current: bool = False


class ModelListItem(ListItem):
    """模型候选列表中的单条可选项。"""

    def __init__(self, entry: ModelEntry):
        self.entry = entry
        primary = f"{entry.alias} *" if entry.current else entry.alias
        summary = picker_line(primary, f"{entry.title} · {entry.subtitle}", limit=68)
        super().__init__(
            Static(summary, classes="picker-item-text"),
            classes="picker-item",
        )


def build_thread_entries(service: Any) -> list[ThreadEntry]:
    """构建线程切换列表使用的线程摘要。"""

    entries: list[ThreadEntry] = []
    for thread_id in service.list_threads():
        thread_store = service.get_thread(thread_id)
        thread_store.reload()

        title = thread_id
        for message in reversed(thread_store.messages):
            content = (message.get("content") or "").strip()
            if content:
                title = one_line(content, limit=42)
                if message["role"] == "user":
                    break

        thread_dir = service.thread_stores.get_thread_dir(thread_id)
        files = [path for path in thread_dir.rglob("*") if path.is_file()] if thread_dir.exists() else []
        total_size = sum(path.stat().st_size for path in files)
        latest_mtime = max(
            (path.stat().st_mtime for path in files),
            default=thread_dir.stat().st_mtime if thread_dir.exists() else 0.0,
        )
        subtitle = f"{format_relative_time(latest_mtime)} · {thread_id} · {format_bytes(total_size)}"
        entries.append(
            ThreadEntry(
                thread_id=thread_id,
                title=title,
                subtitle=subtitle,
                sort_key=latest_mtime,
            )
        )

    return sorted(entries, key=lambda entry: entry.sort_key, reverse=True)


def build_command_entries() -> list[CommandEntry]:
    """构建输入 `/` 时展示的命令候选列表。"""

    return [
        CommandEntry("/help", "显示帮助"),
        CommandEntry("/model", "切换当前模型"),
        CommandEntry("/new", "开启新线程"),
        CommandEntry("/threads", "打开线程切换列表"),
        CommandEntry("/status", "显示当前状态"),
        CommandEntry("/compact", "压缩当前线程"),
        CommandEntry("/banana", "查看全局 / 项目指令"),
        CommandEntry("/clear", "清空当前线程窗口"),
        CommandEntry("/exit", "退出程序"),
    ]


def build_model_entries(service: Any) -> list[ModelEntry]:
    """构建 `/model` 使用的模型候选列表。"""

    entries: list[ModelEntry] = []
    for item in service.list_models():
        caps = item.get("capabilities", {})
        flags = [
            f"stream:{'y' if caps.get('stream') else 'n'}",
            f"tools:{'y' if caps.get('tools') else 'n'}",
            f"reason:{'y' if caps.get('reasoning') else 'n'}",
        ]
        subtitle = f"{item['provider']} · {item['model']} · {' · '.join(flags)}"
        entries.append(
            ModelEntry(
                alias=item["alias"],
                title=item["description"],
                subtitle=subtitle,
                current=item["current"],
            )
        )
    return entries
