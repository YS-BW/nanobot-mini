"""基于 Textual 的可滚动 TUI。

这版把页面收成一张纸：
- 除输入框外，欢迎区、会话正文、thinking、状态都在同一个滚动纸面里
- thinking 在纸面内部展示
- assistant 正文继续流式生长
- 输出区始终自动滚到最新内容
"""

import asyncio
import sys
from dataclasses import dataclass
from datetime import datetime
from textwrap import wrap

from rich.console import Console
from textual import events
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.widgets import Input, ListItem, ListView, Static, TextArea

from .bootstrap import create_app_service
from .contracts import ChatRequest


def _one_line(text: str | None, limit: int = 44) -> str:
    """把多行文本压成单行预览，并做长度截断。"""

    if not text:
        return ""
    compact = " ".join(part.strip() for part in text.splitlines() if part.strip())
    if len(compact) <= limit:
        return compact
    return f"{compact[: limit - 1]}…"


def _status_lines(status: dict) -> list[str]:
    """把会话状态格式化成多行文本。"""

    return [
        f"当前会话: {status['session_id']}",
        f"消息数量: {status['message_count']}",
        f"工作目录: {status['workspace']}",
        f"模型: {status['model']}",
        f"session: {status['paths']['session']}",
        f"history: {status['paths']['history']}",
        f"summary: {status['paths']['summary']}",
        f"memory: {status['paths']['memory']}",
        f"history 条目: {status['history_count']}",
        f"summary 条目: {status['summary_count']}",
        f"memory: {'存在' if status['has_memory'] else '无'}",
    ]


def _banana_lines(info: dict) -> list[str]:
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


def _render_prefixed_block(prefix: str, text: str) -> str:
    """把文本渲染成终端式块。"""

    stripped = (text or "").strip()
    if not stripped:
        return prefix
    lines = stripped.splitlines()
    return "\n".join([f"{prefix} {lines[0]}"] + [f"  {line}" for line in lines[1:]])


def _picker_line(primary: str, secondary: str, limit: int = 72, gap: int = 2) -> str:
    """把列表项压成单行双列，便于做紧凑展示。"""

    left = primary.strip()
    right = secondary.strip()
    if not right:
        return _one_line(left, limit=limit)

    raw = f"{left}{' ' * gap}{right}"
    if len(raw) <= limit:
        return raw

    max_right = max(12, limit - len(left) - gap)
    return f"{left}{' ' * gap}{_one_line(right, limit=max_right)}"


def _format_bytes(size: int) -> str:
    """把字节数转成可读体积。"""

    units = ["B", "KB", "MB", "GB"]
    value = float(size)
    for unit in units:
        if value < 1024 or unit == units[-1]:
            return f"{value:.1f}{unit}" if unit != "B" else f"{int(value)}B"
        value /= 1024
    return f"{int(size)}B"


def _format_relative_time(timestamp: float) -> str:
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


def _wrap_for_box(text: str, width: int = 66) -> list[str]:
    """把 thinking 文本按固定宽度切成多行。"""

    lines: list[str] = []
    for raw_line in text.splitlines() or ([text] if text else []):
        lines.extend(wrap(raw_line, width=width) or [""])
    return lines or ["thinking..."]


def _render_thinking_box(
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


@dataclass
class SessionEntry:
    """会话选择器里展示的一条会话摘要。"""

    session_id: str
    title: str
    subtitle: str
    sort_key: float


class SessionListItem(ListItem):
    """会话选择器中的单条可选项。"""

    def __init__(self, entry: SessionEntry):
        self.entry = entry
        summary = _picker_line(entry.session_id, entry.title, limit=68)
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
        summary = _picker_line(entry.command, entry.description, limit=68)
        super().__init__(
            Static(summary, classes="picker-item-text"),
            classes="picker-item",
        )


class BananaTUI(App[None]):
    """bananabot 的 Textual 终端界面。"""

    CSS = """
    Screen {
        layout: vertical;
        background: #0b0f14;
        color: #dde6f2;
    }

    #paper-shell {
        height: 1fr;
        padding: 1 1 0 1;
        background: #0b0f14;
    }

    #paper-view {
        height: 1fr;
        border: round #2a3340;
        background: #11161d;
        color: #dde6f2;
        padding: 0 1;
        scrollbar-background: #11161d;
        scrollbar-color: #334155;
        scrollbar-color-hover: #475569;
        scrollbar-corner-color: #11161d;
    }

    #input-shell {
        height: auto;
        padding: 0 1 1 1;
        border-top: solid #202833;
        background: #0b0f14;
    }

    #session-picker-inline,
    #command-picker-inline {
        display: none;
        height: auto;
        max-height: 8;
        margin: 0;
        padding: 0 0 0 2;
        border: none;
        background: #0b0f14;
    }

    #session-picker-inline.-open,
    #command-picker-inline.-open {
        display: block;
    }

    #session-picker-search {
        height: auto;
        background: #0b0f14;
        border: none;
        color: #9aa7b8;
        padding: 0;
        margin: 0 0 1 0;
    }

    #session-picker-list,
    #command-picker-list {
        height: auto;
        max-height: 8;
        background: #0b0f14;
        border: none;
    }

    .picker-item {
        padding: 0;
        margin: 0;
    }

    .picker-item-text {
        color: #cdd6e3;
    }

    #input-bar {
        height: 1;
        margin-top: 0;
        border: none;
        background: #0b0f14;
        color: #f7f9fc;
        padding: 0;
    }
    """

    BINDINGS = [
        Binding("ctrl+c", "quit", "退出"),
        Binding("ctrl+l", "clear_process", "清空过程"),
        Binding("ctrl+r", "reload_session", "重载会话"),
        Binding("escape", "focus_input", "聚焦输入"),
    ]

    def __init__(self, service):
        super().__init__()
        self.service = service
        self.session = service.get_session("cli:default")
        self.busy = False
        self._body_blocks: list[str] = []
        self._thinking_slot_index: int | None = None
        self._live_assistant_index: int | None = None
        self._reasoning_buffer = ""
        self._round_tools: list[str] = []
        self._status_extra: str | None = None
        self._session_entries: list[SessionEntry] = []
        self._filtered_session_entries: list[SessionEntry] = []
        self._command_entries = self._build_command_entries()
        self._filtered_command_entries: list[CommandEntry] = []
        self._suppress_command_picker_refresh = False

    def compose(self) -> ComposeResult:
        with Vertical(id="paper-shell"):
            yield TextArea(
                read_only=True,
                show_line_numbers=False,
                show_cursor=False,
                soft_wrap=True,
                id="paper-view",
            )
        with Vertical(id="input-shell"):
            yield Input(placeholder="❯ 给 bananabot 发消息，或者输入 /help", id="input-bar")
            with Vertical(id="session-picker-inline"):
                yield Input(placeholder="⌕ Search sessions…", id="session-picker-search")
                yield ListView(id="session-picker-list")
            with Vertical(id="command-picker-inline"):
                yield ListView(id="command-picker-list")

    @property
    def main_view(self) -> TextArea:
        return self.query_one("#paper-view", TextArea)

    @property
    def input_bar(self) -> Input:
        return self.query_one("#input-bar", Input)

    @property
    def command_picker(self) -> Vertical:
        return self.query_one("#command-picker-inline", Vertical)

    @property
    def command_picker_list(self) -> ListView:
        return self.query_one("#command-picker-list", ListView)

    @property
    def session_picker(self) -> Vertical:
        return self.query_one("#session-picker-inline", Vertical)

    @property
    def session_picker_search(self) -> Input:
        return self.query_one("#session-picker-search", Input)

    @property
    def session_picker_list(self) -> ListView:
        return self.query_one("#session-picker-list", ListView)

    def on_mount(self) -> None:
        """初始化界面状态。"""

        self.title = "bananabot TUI"
        self.sub_title = self.session.key
        self._rebuild_body_from_session()
        self._append_info_block("ready")
        self._append_info_block("/help 查看命令")
        self._sync_page()
        self.input_bar.focus()

    def action_focus_input(self) -> None:
        """把焦点切回输入框。"""

        if self.session_picker.has_class("-open"):
            self._hide_session_picker()
            return
        if self.command_picker.has_class("-open"):
            self._hide_command_picker()
            return
        self.input_bar.focus()

    def action_clear_process(self) -> None:
        """清空当前纸面中的临时过程，保留持久化正文。"""

        self._rebuild_body_from_session()
        self._append_info_block("已清理当前屏幕的临时过程")
        self._sync_page()

    def action_reload_session(self) -> None:
        """从磁盘重新加载当前会话。"""

        self.session.reload()
        self._rebuild_body_from_session()
        self._append_info_block(f"已重新加载会话 {self.session.key}")
        self._sync_page()

    def _build_recent_text(self) -> str:
        """根据现有会话生成最近活动摘要。"""

        session_ids = list(reversed(self.service.list_sessions()))
        lines: list[str] = []
        for session_id in session_ids:
            session = self.service.get_session(session_id)
            session.reload()
            if not session.messages:
                continue
            preview = _one_line(session.messages[-1].get("content", ""), limit=26)
            lines.append(f"- {session_id}: {preview or '有历史消息'}")
            if len(lines) >= 3:
                break
        if not lines:
            return "- No recent activity"
        return "\n".join(lines)

    def _build_session_entries(self) -> list[SessionEntry]:
        """构建 /sessions 使用的会话摘要列表。"""

        entries: list[SessionEntry] = []
        for session_id in self.service.list_sessions():
            session = self.service.get_session(session_id)
            session.reload()

            title = session_id
            for message in reversed(session.messages):
                content = (message.get("content") or "").strip()
                if content:
                    title = _one_line(content, limit=42)
                    if message["role"] == "user":
                        break

            session_dir = self.service.sessions._get_session_dir(session_id)
            files = [path for path in session_dir.rglob("*") if path.is_file()] if session_dir.exists() else []
            total_size = sum(path.stat().st_size for path in files)
            latest_mtime = max((path.stat().st_mtime for path in files), default=session_dir.stat().st_mtime if session_dir.exists() else 0.0)
            subtitle = f"{_format_relative_time(latest_mtime)} · {session_id} · {_format_bytes(total_size)}"
            entries.append(
                SessionEntry(
                    session_id=session_id,
                    title=title,
                    subtitle=subtitle,
                    sort_key=latest_mtime,
                )
            )

        return sorted(entries, key=lambda entry: entry.sort_key, reverse=True)

    @staticmethod
    def _build_command_entries() -> list[CommandEntry]:
        """构建输入 `/` 时展示的命令候选列表。"""

        return [
            CommandEntry("/help", "显示帮助"),
            CommandEntry("/new", "开启新会话"),
            CommandEntry("/sessions", "打开会话切换列表"),
            CommandEntry("/status", "显示当前状态"),
            CommandEntry("/compact", "压缩当前会话"),
            CommandEntry("/banana", "查看全局 / 项目指令"),
            CommandEntry("/clear", "清空当前会话窗口"),
            CommandEntry("/exit", "退出程序"),
        ]

    def _build_welcome_block(self) -> str:
        """生成纸面顶部的欢迎区。"""

        status = self.service.get_status(self.session.key)
        busy_text = "busy" if self.busy else "ready"
        ctx_window = max(1, getattr(self.service.config, "context_window", 1))
        ctx_percent = min(100, int(self.session.estimate_tokens() / ctx_window * 100))

        lines = [
            "bananabot",
            "",
            "Welcome back!",
            "",
            "▐▛███▜▌",
            "▝▜█████▛▘",
            "  ▘▘ ▝▝",
            "",
            f"{status['model']} · {self.session.key}",
            f"{status['workspace']}",
            "",
            "Tips for getting started",
            "- /help 查看内置命令",
            "- /new 创建新会话",
            "- /compact 压缩当前上下文",
            "- /banana 查看指令文件",
            "",
            "Recent activity",
            self._build_recent_text(),
            "",
            f"Context {ctx_percent}% · {busy_text}" + (f" · {self._status_extra}" if self._status_extra else ""),
            "",
            "─" * 74,
        ]
        return "\n".join(lines)

    def _sync_page(self) -> None:
        """同步整张纸面的内容，并自动滚到底。"""

        parts = [self._build_welcome_block()]
        if self._body_blocks:
            parts.append("\n\n".join(block for block in self._body_blocks if block).rstrip())
        self.main_view.load_text("\n\n".join(part for part in parts if part).rstrip())
        self.main_view.move_cursor(self.main_view.document.end)
        self.call_after_refresh(lambda: self.main_view.scroll_end(animate=False))
        self.sub_title = self.session.key

    def _show_session_picker(self) -> None:
        """在输入区上方展开会话切换列表。"""

        self._hide_command_picker()
        entries = self._build_session_entries()
        if not entries:
            self._append_info_block("当前没有可恢复的会话")
            return

        self._session_entries = entries
        self.session_picker.add_class("-open")
        self.session_picker_search.value = ""
        self._refresh_session_picker("")
        self.call_after_refresh(self.session_picker_search.focus)

    def _hide_session_picker(self) -> None:
        """收起会话切换列表，并把焦点还给主输入框。"""

        self.session_picker.remove_class("-open")
        self.session_picker_search.value = ""
        self._session_entries = []
        self._filtered_session_entries = []
        self.session_picker_list.clear()
        self.call_after_refresh(self.input_bar.focus)

    def _refresh_session_picker(self, query: str) -> None:
        """按搜索词刷新内联会话候选列表。"""

        normalized = query.strip().lower()
        if not normalized:
            self._filtered_session_entries = self._session_entries
        else:
            self._filtered_session_entries = [
                entry
                for entry in self._session_entries
                if normalized in entry.session_id.lower() or normalized in entry.title.lower()
            ]

        self.session_picker_list.clear()
        for entry in self._filtered_session_entries:
            self.session_picker_list.append(SessionListItem(entry))
        self.session_picker_list.index = 0 if self._filtered_session_entries else None

    def _show_command_picker(self) -> None:
        """展开 `/` 命令候选列表。"""

        if self.session_picker.has_class("-open"):
            return
        self.command_picker.add_class("-open")

    def _hide_command_picker(self) -> None:
        """收起命令候选列表。"""

        self.command_picker.remove_class("-open")
        self._filtered_command_entries = []
        self.command_picker_list.clear()

    def _refresh_command_picker(self, query: str) -> None:
        """根据输入框里的 `/` 前缀过滤命令候选。"""

        normalized = query.strip().lower()
        if not normalized.startswith("/"):
            self._hide_command_picker()
            return

        if normalized == "/":
            self._filtered_command_entries = self._command_entries
        else:
            self._filtered_command_entries = [
                entry
                for entry in self._command_entries
                if entry.command.startswith(normalized) or normalized in entry.description.lower()
            ]

        if not self._filtered_command_entries:
            self._hide_command_picker()
            return

        self._show_command_picker()
        self.command_picker_list.clear()
        for entry in self._filtered_command_entries:
            self.command_picker_list.append(CommandListItem(entry))
        self.command_picker_list.index = 0

    def _current_command_entry(self) -> CommandEntry | None:
        """拿到当前高亮的命令候选项。"""

        highlighted = self.command_picker_list.highlighted_child
        if isinstance(highlighted, CommandListItem):
            return highlighted.entry
        if self._filtered_command_entries:
            return self._filtered_command_entries[0]
        return None

    def _move_command_picker_selection(self, step: int) -> None:
        """按方向键移动命令候选高亮项。"""

        if not self._filtered_command_entries:
            return

        current_index = self.command_picker_list.index
        if current_index is None:
            current_index = 0

        next_index = max(0, min(len(self._filtered_command_entries) - 1, current_index + step))
        self.command_picker_list.index = next_index

    def _apply_command_suggestion(self, command: str) -> None:
        """把当前命令候选写回输入框。"""

        self._suppress_command_picker_refresh = True
        self.input_bar.value = command
        self._hide_command_picker()
        self.input_bar.focus()
        self.call_after_refresh(self._finish_command_suggestion_refresh)

    def _finish_command_suggestion_refresh(self) -> None:
        """在下一轮刷新后解除命令候选刷新抑制。"""

        self._suppress_command_picker_refresh = False

    def _execute_command_suggestion(self, command: str) -> None:
        """直接执行当前高亮的命令候选。"""

        self.input_bar.value = ""
        self._hide_command_picker()
        self.run_worker(self._run_command(command), exclusive=True, group="cli-command")

    def _current_session_entry(self) -> SessionEntry | None:
        """拿到当前高亮的会话项。"""

        highlighted = self.session_picker_list.highlighted_child
        if isinstance(highlighted, SessionListItem):
            return highlighted.entry
        if self._filtered_session_entries:
            return self._filtered_session_entries[0]
        return None

    def _move_session_picker_selection(self, step: int) -> None:
        """按方向键移动会话列表高亮项。"""

        if not self._filtered_session_entries:
            return

        current_index = self.session_picker_list.index
        if current_index is None:
            current_index = 0

        next_index = max(0, min(len(self._filtered_session_entries) - 1, current_index + step))
        self.session_picker_list.index = next_index

    def _switch_session(self, session_id: str) -> None:
        """切换当前会话，并刷新纸面正文。"""

        self.session = self.service.get_session(session_id)
        self._rebuild_body_from_session()
        self._append_info_block(f"已切换到会话 {self.session.key}")
        self._hide_session_picker()
        self._sync_page()

    def _render_persisted_messages(self) -> list[str]:
        """把当前 session 里的 user/assistant 消息渲染成纸面正文。"""

        self.session.reload()
        blocks: list[str] = []
        for message in self.session.messages:
            if message["role"] == "user":
                blocks.append(_render_prefixed_block("❯", message.get("content", "")))
            elif message["role"] == "assistant":
                blocks.append(_render_prefixed_block("⏺", message.get("content", "")))
        return blocks

    def _rebuild_body_from_session(self) -> None:
        """基于持久化消息重建纸面正文。"""

        self._body_blocks = self._render_persisted_messages()
        self._thinking_slot_index = None
        self._live_assistant_index = None
        self._reasoning_buffer = ""
        self._round_tools = []

    def _append_body_block(self, text: str) -> int:
        """在正文末尾追加一个块，并返回索引。"""

        self._body_blocks.append(text)
        self._sync_page()
        return len(self._body_blocks) - 1

    def _replace_body_block(self, index: int | None, text: str) -> int:
        """替换指定块；如果索引不存在则追加。"""

        if index is None or index >= len(self._body_blocks):
            return self._append_body_block(text)
        self._body_blocks[index] = text
        self._sync_page()
        return index

    def _append_info_block(self, text: str) -> int:
        """追加系统/命令输出块。"""

        return self._append_body_block(_render_prefixed_block("⏺", text))

    def _append_user_block(self, text: str) -> int:
        """追加用户输入块。"""

        return self._append_body_block(_render_prefixed_block("❯", text))

    def _ensure_thinking_slot(self) -> None:
        """确保当前轮次存在 thinking 占位槽。"""

        if self._thinking_slot_index is None:
            self._thinking_slot_index = self._append_body_block("")

    def _render_live_thinking_box(self) -> str:
        """渲染执行中的 thinking 框。"""

        lines = _wrap_for_box(self._reasoning_buffer)
        lines.extend([f"tool: {tool}" for tool in self._round_tools])
        return _render_thinking_box("thinking", lines, max_height=5, min_height=5)

    def _append_reasoning_chunk(self, chunk: str) -> None:
        """把模型思考增量拼进 thinking 框。"""

        if not chunk:
            return
        self._ensure_thinking_slot()
        self._reasoning_buffer += chunk
        self._thinking_slot_index = self._replace_body_block(
            self._thinking_slot_index,
            self._render_live_thinking_box(),
        )

    def _record_tool_call(self, tool_name: str) -> None:
        """记录本轮调用过的工具，并刷新 thinking 框。"""

        if not tool_name:
            return
        if tool_name not in self._round_tools:
            self._round_tools.append(tool_name)
        self._ensure_thinking_slot()
        self._thinking_slot_index = self._replace_body_block(
            self._thinking_slot_index,
            self._render_live_thinking_box(),
        )

    def _finalize_thinking(self) -> None:
        """根据本轮执行结果收口 thinking 展示。"""

        if self._thinking_slot_index is None:
            return

        if self._round_tools:
            summary_lines = ["tools"] + self._round_tools[:4]
            self._thinking_slot_index = self._replace_body_block(
                self._thinking_slot_index,
                _render_thinking_box("thinking", summary_lines, max_height=5),
            )
        else:
            self._thinking_slot_index = self._replace_body_block(
                self._thinking_slot_index,
                "**Thinked**",
            )

        self._reasoning_buffer = ""

    def _append_assistant_delta(self, delta: str) -> None:
        """把 assistant 正文增量写进正文。"""

        if self._live_assistant_index is None:
            self._live_assistant_index = self._append_body_block(_render_prefixed_block("⏺", delta))
            return

        current_text = self._body_blocks[self._live_assistant_index]
        prefix = "⏺ "
        content = current_text[len(prefix):] if current_text.startswith(prefix) else current_text
        content = content.replace("\n  ", "\n")
        content += delta
        self._live_assistant_index = self._replace_body_block(
            self._live_assistant_index,
            _render_prefixed_block("⏺", content),
        )

    def _finalize_assistant_block(self, text: str) -> None:
        """在无增量正文时，用最终回复补齐 assistant 块。"""

        if self._live_assistant_index is None:
            self._live_assistant_index = self._append_body_block(_render_prefixed_block("⏺", text))

    def _set_busy(self, busy: bool, extra: str | None = None) -> None:
        """统一控制忙闲状态和输入框可用性。"""

        self.busy = busy
        self._status_extra = extra
        self.input_bar.disabled = busy
        self.session_picker_search.disabled = busy
        self._sync_page()
        if not busy:
            if self.session_picker.has_class("-open"):
                self.session_picker_search.focus()
            else:
                self.input_bar.focus()

    def on_input_changed(self, event: Input.Changed) -> None:
        """处理输入框变更；用于实时过滤候选列表。"""

        if event.input.id == "session-picker-search":
            self._refresh_session_picker(event.value)
            return

        if event.input.id == "input-bar" and not self.busy:
            if self._suppress_command_picker_refresh:
                return
            self._refresh_command_picker(event.value)

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        """鼠标或回车选择内联候选项。"""

        if event.list_view.id == "session-picker-list" and isinstance(event.item, SessionListItem):
            self._switch_session(event.item.entry.session_id)
            return

        if event.list_view.id == "command-picker-list" and isinstance(event.item, CommandListItem):
            self._execute_command_suggestion(event.item.entry.command)

    def on_key(self, event: events.Key) -> None:
        """处理候选列表打开时的全局按键。"""

        if self.command_picker.has_class("-open"):
            if event.key == "up":
                self._move_command_picker_selection(-1)
                event.stop()
                return

            if event.key == "down":
                self._move_command_picker_selection(1)
                event.stop()
                return

        if not self.session_picker.has_class("-open"):
            return

        if event.key == "up":
            self._move_session_picker_selection(-1)
            event.stop()
            return

        if event.key == "down":
            self._move_session_picker_selection(1)
            event.stop()

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        """处理输入提交。"""

        if event.input.id == "session-picker-search":
            selected = self._current_session_entry()
            if selected is None:
                self._append_info_block("没有匹配的会话")
                self._hide_session_picker()
                self._sync_page()
                return
            self._switch_session(selected.session_id)
            return

        text = event.value.strip()
        if not text:
            return

        if self.busy:
            self._append_info_block("当前还有任务在跑")
            return

        if event.input.id == "input-bar" and self.command_picker.has_class("-open"):
            selected_command = self._current_command_entry()
            if selected_command is not None:
                self._execute_command_suggestion(selected_command.command)
                return

        self.input_bar.value = ""
        self._hide_command_picker()

        if text.startswith("/"):
            self.run_worker(self._run_command(text), exclusive=True, group="cli-command")
            return

        self.run_worker(self._run_chat(text), exclusive=True, group="chat")

    async def _run_command(self, command: str) -> None:
        """处理 TUI 内置命令。"""

        command = command.strip()
        lower = command.lower()
        self._append_user_block(command)

        if lower == "/help":
            self._append_info_block(
                "\n".join(
                    [
                        "可用命令:",
                        "  /new              开启新会话",
                        "  /sessions         打开会话切换列表",
                        "  /clear            清空当前会话窗口",
                        "  /status           显示当前状态",
                        "  /compact          压缩当前会话",
                        "  /banana           查看全局/项目指令",
                        "  /help             显示帮助",
                        "  /exit             退出程序",
                    ]
                )
            )
            return

        if lower == "/exit":
            self.exit()
            return

        if lower == "/new":
            self.session = self.service.create_session()
            self._rebuild_body_from_session()
            self._append_info_block(f"已开启新会话 {self.session.key}")
            self._sync_page()
            return

        if lower == "/sessions":
            self._show_session_picker()
            return

        if lower == "/clear":
            self.service.clear_session(self.session.key)
            self._rebuild_body_from_session()
            self._append_info_block(f"已清空会话 {self.session.key} 的当前窗口")
            self._sync_page()
            return

        if lower == "/status":
            self._append_info_block("\n".join(_status_lines(self.service.get_status(self.session.key))))
            return

        if lower == "/banana":
            self._append_info_block("\n".join(_banana_lines(self.service.get_banana_info())))
            return

        if lower == "/compact":
            self._set_busy(True, extra="compact 中")
            try:
                result = await self.service.compact_session(self.session.key, force=True)
                self._rebuild_body_from_session()
                if not result["did_compact"]:
                    self._append_info_block("当前无需压缩")
                elif result["has_memory"]:
                    self._append_info_block("compact 完成，内容已整合到 MEMORY.md")
                else:
                    self._append_info_block(
                        f"compact 完成，摘要已保存（当前 {result['summary_count']} 条）"
                    )
                self._sync_page()
            except Exception as exc:  # pragma: no cover
                self._append_info_block(f"compact 失败: {exc}")
            finally:
                self._set_busy(False)
            return

        self._append_info_block(f"未知命令: {command}")

    async def _run_chat(self, user_message: str) -> None:
        """执行一次聊天，并把事件流实时写入纸面正文。"""

        self._reasoning_buffer = ""
        self._round_tools = []
        self._thinking_slot_index = None
        self._live_assistant_index = None
        self._append_user_block(user_message)
        self._ensure_thinking_slot()
        self._set_busy(True, extra="对话中")

        try:
            async for event in self.service.chat_stream(
                ChatRequest(session_id=self.session.key, user_input=user_message)
            ):
                if event.type == "assistant_thinking":
                    continue
                if event.type == "assistant_reasoning_delta":
                    delta = (event.data or {}).get("delta") or event.message or ""
                    self._append_reasoning_chunk(delta)
                elif event.type == "tool_call_started":
                    self._record_tool_call(((event.data or {}).get("tool_name")) or "")
                elif event.type == "assistant_delta":
                    delta = (event.data or {}).get("delta") or event.message or ""
                    if delta:
                        self._append_assistant_delta(delta)
                elif event.type == "error":
                    self._finalize_thinking()
                    if event.message:
                        self._append_info_block(event.message)
                elif event.type == "assistant_message":
                    self._finalize_thinking()
                    self._finalize_assistant_block(event.message or "[无回复内容]")
                elif event.type == "done":
                    self._finalize_thinking()

            self._status_extra = "已完成"
            self._sync_page()
        except Exception as exc:  # pragma: no cover
            self._finalize_thinking()
            self._append_info_block(f"对话执行失败: {exc}")
        finally:
            self._set_busy(False)
            self._thinking_slot_index = None
            self._live_assistant_index = None
            self._round_tools = []
            self._status_extra = None
            self._sync_page()


async def run_once(user_message: str) -> None:
    """命令行单次模式。"""

    console = Console()
    service = create_app_service()
    printed = False
    async for event in service.chat_stream(ChatRequest(session_id="cli:default", user_input=user_message)):
        if event.type == "assistant_delta":
            delta = (event.data or {}).get("delta") or event.message or ""
            if delta:
                if not printed:
                    console.print("bananabot", style="cyan", end="\n")
                    printed = True
                console.print(delta, end="", soft_wrap=True)
        elif event.type == "assistant_message" and not printed:
            console.print("bananabot", style="cyan")
            console.print(event.message or "[无回复内容]", end="")
            printed = True
        elif event.type == "error":
            console.print(f"\nerror: {event.message}", style="red")

    if printed:
        console.print()


def main() -> None:
    """CLI 入口。"""

    if len(sys.argv) < 2:
        BananaTUI(create_app_service()).run()
        return

    asyncio.run(run_once(" ".join(sys.argv[1:])))
