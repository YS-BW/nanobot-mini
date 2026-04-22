"""基于 Textual 的可滚动 TUI。

这版把页面收成一张纸：
- 除输入框外，欢迎区、线程正文、thinking、状态都在同一个滚动纸面里
- thinking 在纸面内部展示
- assistant 正文继续流式生长
- 输出区始终自动滚到最新内容

同时把命令执行、事件流消费、纸面状态、候选列表构建拆到独立模块，
避免这个文件继续承担界面层和业务编排两层职责。
"""

from __future__ import annotations

import asyncio
import sys

from rich.console import Console
from textual import events
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.widgets import Input, ListView, TextArea

from .bootstrap import create_app_service
from .cli_handlers import CLICommandHandler, CLIConversationHandler
from .cli_lists import (
    CommandEntry,
    CommandListItem,
    ModelEntry,
    ModelListItem,
    ThreadEntry,
    ThreadListItem,
    build_command_entries,
    build_model_entries,
    build_thread_entries,
)
from .cli_render import one_line
from .cli_state import PaperState
from .contracts import TaskRequest


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

    #thread-picker-inline,
    #command-picker-inline,
    #model-picker-inline {
        display: none;
        height: auto;
        max-height: 8;
        margin: 0;
        padding: 0 0 0 2;
        border: none;
        background: #0b0f14;
    }

    #thread-picker-inline.-open,
    #command-picker-inline.-open,
    #model-picker-inline.-open {
        display: block;
    }

    #thread-picker-search {
        height: auto;
        background: #0b0f14;
        border: none;
        color: #9aa7b8;
        padding: 0;
        margin: 0 0 1 0;
    }

    #thread-picker-list,
    #command-picker-list,
    #model-picker-list {
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
        Binding("ctrl+r", "reload_thread", "重载线程"),
        Binding("escape", "focus_input", "聚焦输入"),
    ]

    def __init__(self, service):
        super().__init__()
        self.service = service
        self.thread_store = service.get_thread("cli:default")
        self.busy = False
        self.paper_state = PaperState()
        self.status_extra: str | None = None
        self._thread_entries: list[ThreadEntry] = []
        self._filtered_thread_entries: list[ThreadEntry] = []
        self._command_entries = build_command_entries()
        self._filtered_command_entries: list[CommandEntry] = []
        self._model_entries: list[ModelEntry] = []
        self._suppress_command_picker_refresh = False
        self.command_handler = CLICommandHandler(self)
        self.conversation_handler = CLIConversationHandler(self)

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
            with Vertical(id="thread-picker-inline"):
                yield Input(placeholder="⌕ Search threads…", id="thread-picker-search")
                yield ListView(id="thread-picker-list")
            with Vertical(id="command-picker-inline"):
                yield ListView(id="command-picker-list")
            with Vertical(id="model-picker-inline"):
                yield ListView(id="model-picker-list")

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
    def thread_picker(self) -> Vertical:
        return self.query_one("#thread-picker-inline", Vertical)

    @property
    def thread_picker_search(self) -> Input:
        return self.query_one("#thread-picker-search", Input)

    @property
    def thread_picker_list(self) -> ListView:
        return self.query_one("#thread-picker-list", ListView)

    @property
    def model_picker(self) -> Vertical:
        return self.query_one("#model-picker-inline", Vertical)

    @property
    def model_picker_list(self) -> ListView:
        return self.query_one("#model-picker-list", ListView)

    def on_mount(self) -> None:
        """初始化界面状态。"""

        self.title = "bananabot TUI"
        self.sub_title = self.thread_store.key
        self.rebuild_body_from_thread()
        self.append_info_block("ready")
        self.append_info_block("/help 查看命令")
        self.sync_page()
        self.input_bar.focus()

    def action_focus_input(self) -> None:
        """把焦点切回输入框。"""

        if self.thread_picker.has_class("-open"):
            self.hide_thread_picker()
            return
        if self.command_picker.has_class("-open"):
            self.hide_command_picker()
            return
        if self.model_picker.has_class("-open"):
            self.hide_model_picker()
            return
        self.input_bar.focus()

    def action_clear_process(self) -> None:
        """清空当前纸面中的临时过程，保留持久化正文。"""

        self.rebuild_body_from_thread()
        self.append_info_block("已清理当前屏幕的临时过程")
        self.sync_page()

    def action_reload_thread(self) -> None:
        """从磁盘重新加载当前线程。"""

        self.thread_store.reload()
        self.rebuild_body_from_thread()
        self.append_info_block(f"已重新加载线程 {self.thread_store.key}")
        self.sync_page()

    def _build_recent_text(self) -> str:
        """根据现有线程生成最近活动摘要。"""

        thread_ids = list(reversed(self.service.list_threads()))
        lines: list[str] = []
        for thread_id in thread_ids:
            thread_store = self.service.get_thread(thread_id)
            thread_store.reload()
            if not thread_store.messages:
                continue
            preview = one_line(thread_store.messages[-1].get("content", ""), limit=26)
            lines.append(f"- {thread_id}: {preview or '有历史消息'}")
            if len(lines) >= 3:
                break
        if not lines:
            return "- No recent activity"
        return "\n".join(lines)

    def build_thread_entries(self) -> list[ThreadEntry]:
        """委托列表构建模块生成线程摘要。"""

        return build_thread_entries(self.service)

    def build_model_entries(self) -> list[ModelEntry]:
        """委托列表构建模块生成模型摘要。"""

        return build_model_entries(self.service)

    def _build_welcome_block(self) -> str:
        """生成纸面顶部的欢迎区。"""

        status = self.service.get_thread_status(self.thread_store.key)
        busy_text = "busy" if self.busy else "ready"
        ctx_window = max(1, getattr(self.service.config, "context_window", 1))
        ctx_percent = min(100, int(self.thread_store.estimate_tokens() / ctx_window * 100))

        lines = [
            "bananabot",
            "",
            "Welcome back!",
            "",
            "▐▛███▜▌",
            "▝▜█████▛▘",
            "  ▘▘ ▝▝",
            "",
            f"{status.get('model_alias', status['model'])} -> {status['model']} · {self.thread_store.key}",
            f"{status['workspace']}",
            "",
            "Tips for getting started",
            "- /help 查看内置命令",
            "- /new 创建新线程",
            "- /compact 压缩当前上下文",
            "- /banana 查看指令文件",
            "",
            "Recent activity",
            self._build_recent_text(),
            "",
            f"Context {ctx_percent}% · {busy_text}" + (f" · {self.status_extra}" if self.status_extra else ""),
            "",
            "─" * 74,
        ]
        return "\n".join(lines)

    def sync_page(self) -> None:
        """同步整张纸面的内容，并自动滚到底。"""

        self.main_view.load_text(self.paper_state.render_document(self._build_welcome_block()))
        self.main_view.move_cursor(self.main_view.document.end)
        self.call_after_refresh(lambda: self.main_view.scroll_end(animate=False))
        self.sub_title = self.thread_store.key

    def show_thread_picker(self) -> None:
        """在输入区上方展开线程切换列表。"""

        self.hide_command_picker()
        self.hide_model_picker()
        entries = self.build_thread_entries()
        if not entries:
            self.append_info_block("当前没有可恢复的线程")
            return

        self._thread_entries = entries
        self.thread_picker.add_class("-open")
        self.thread_picker_search.value = ""
        self._refresh_thread_picker("")
        self.call_after_refresh(self.thread_picker_search.focus)

    def hide_thread_picker(self) -> None:
        """收起线程切换列表，并把焦点还给主输入框。"""

        self.thread_picker.remove_class("-open")
        self.thread_picker_search.value = ""
        self._thread_entries = []
        self._filtered_thread_entries = []
        self.thread_picker_list.clear()
        self.call_after_refresh(self.input_bar.focus)

    def _refresh_thread_picker(self, query: str) -> None:
        """按搜索词刷新内联线程候选列表。"""

        normalized = query.strip().lower()
        if not normalized:
            self._filtered_thread_entries = self._thread_entries
        else:
            self._filtered_thread_entries = [
                entry
                for entry in self._thread_entries
                if normalized in entry.thread_id.lower() or normalized in entry.title.lower()
            ]

        self.thread_picker_list.clear()
        for entry in self._filtered_thread_entries:
            self.thread_picker_list.append(ThreadListItem(entry))
        self.thread_picker_list.index = 0 if self._filtered_thread_entries else None

    def show_command_picker(self) -> None:
        """展开 `/` 命令候选列表。"""

        self.hide_model_picker()
        if self.thread_picker.has_class("-open"):
            return
        self.command_picker.add_class("-open")

    def hide_command_picker(self) -> None:
        """收起命令候选列表。"""

        self.command_picker.remove_class("-open")
        self._filtered_command_entries = []
        self.command_picker_list.clear()

    def show_model_picker(self) -> None:
        """展开模型切换列表。"""

        self.hide_command_picker()
        if self.thread_picker.has_class("-open"):
            self.hide_thread_picker()

        entries = self.build_model_entries()
        if not entries:
            self.append_info_block("当前没有可切换的模型")
            return

        self._model_entries = entries
        self.model_picker.add_class("-open")
        self.model_picker_list.clear()
        for entry in self._model_entries:
            self.model_picker_list.append(ModelListItem(entry))
        self.model_picker_list.index = 0

    def hide_model_picker(self) -> None:
        """收起模型切换列表。"""

        self.model_picker.remove_class("-open")
        self._model_entries = []
        self.model_picker_list.clear()

    def _current_model_entry(self) -> ModelEntry | None:
        """拿到当前高亮的模型项。"""

        highlighted = self.model_picker_list.highlighted_child
        if isinstance(highlighted, ModelListItem):
            return highlighted.entry
        if self._model_entries:
            return self._model_entries[0]
        return None

    def _move_model_picker_selection(self, step: int) -> None:
        """按方向键移动模型列表高亮项。"""

        if not self._model_entries:
            return

        current_index = self.model_picker_list.index
        if current_index is None:
            current_index = 0

        next_index = max(0, min(len(self._model_entries) - 1, current_index + step))
        self.model_picker_list.index = next_index

    def switch_model(self, alias: str) -> None:
        """切换当前模型并刷新纸面。"""

        profile = self.service.switch_model(alias)
        caps = profile.get("capabilities", {})
        flags = [
            f"stream:{'y' if caps.get('stream') else 'n'}",
            f"tools:{'y' if caps.get('tools') else 'n'}",
            f"reason:{'y' if caps.get('reasoning') else 'n'}",
        ]
        self.append_info_block(
            "\n".join(
                [
                    f"已切换模型 {profile['alias']} -> {profile['model']}",
                    f"provider: {profile['provider']}",
                    f"capabilities: {' · '.join(flags)}",
                ]
            )
        )
        self.hide_model_picker()
        self.sync_page()

    def _refresh_command_picker(self, query: str) -> None:
        """根据输入框里的 `/` 前缀过滤命令候选。"""

        normalized = query.strip().lower()
        if not normalized.startswith("/"):
            self.hide_command_picker()
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
            self.hide_command_picker()
            return

        self.show_command_picker()
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
        self.hide_command_picker()
        self.input_bar.focus()
        self.call_after_refresh(self._finish_command_suggestion_refresh)

    def _finish_command_suggestion_refresh(self) -> None:
        """在下一轮刷新后解除命令候选刷新抑制。"""

        self._suppress_command_picker_refresh = False

    def _execute_command_suggestion(self, command: str) -> None:
        """直接执行当前高亮的命令候选。"""

        self.input_bar.value = ""
        self.hide_command_picker()
        self.run_worker(self.command_handler.run(command), exclusive=True, group="cli-command")

    def _current_thread_entry(self) -> ThreadEntry | None:
        """拿到当前高亮的线程项。"""

        highlighted = self.thread_picker_list.highlighted_child
        if isinstance(highlighted, ThreadListItem):
            return highlighted.entry
        if self._filtered_thread_entries:
            return self._filtered_thread_entries[0]
        return None

    def _move_thread_picker_selection(self, step: int) -> None:
        """按方向键移动线程列表高亮项。"""

        if not self._filtered_thread_entries:
            return

        current_index = self.thread_picker_list.index
        if current_index is None:
            current_index = 0

        next_index = max(0, min(len(self._filtered_thread_entries) - 1, current_index + step))
        self.thread_picker_list.index = next_index

    def switch_thread(self, thread_id: str) -> None:
        """切换当前线程，并刷新纸面正文。"""

        self.thread_store = self.service.get_thread(thread_id)
        self.rebuild_body_from_thread()
        self.append_info_block(f"已切换到线程 {self.thread_store.key}")
        self.hide_thread_picker()
        self.sync_page()

    def rebuild_body_from_thread(self) -> None:
        """基于持久化消息重建纸面正文。"""

        self.thread_store.reload()
        self.paper_state.rebuild_from_thread_messages(self.thread_store.messages)

    def append_info_block(self, text: str) -> None:
        """追加系统/命令输出块。"""

        self.paper_state.append_info_block(text)
        self.sync_page()

    def append_user_block(self, text: str) -> None:
        """追加用户输入块。"""

        self.paper_state.append_user_block(text)
        self.sync_page()

    def ensure_thinking_slot(self) -> None:
        """确保当前轮存在 thinking 占位槽。"""

        self.paper_state.ensure_thinking_slot()
        self.sync_page()

    def append_reasoning_chunk(self, chunk: str) -> None:
        """把模型思考增量拼进 thinking 框。"""

        self.paper_state.append_reasoning_chunk(chunk)
        self.sync_page()

    def record_tool_call(self, tool_name: str) -> None:
        """记录本轮调用过的工具，并刷新 thinking 框。"""

        self.paper_state.record_tool_call(tool_name)
        self.sync_page()

    def finalize_thinking(self) -> None:
        """根据本轮执行结果收口 thinking 展示。"""

        self.paper_state.finalize_thinking()
        self.sync_page()

    def append_assistant_delta(self, delta: str) -> None:
        """把 assistant 正文增量写进正文。"""

        self.paper_state.append_assistant_delta(delta)
        self.sync_page()

    def finalize_assistant_block(self, text: str) -> None:
        """在无增量正文时，用最终回复补齐 assistant 块。"""

        self.paper_state.finalize_assistant_block(text)
        self.sync_page()

    def set_busy(self, busy: bool, extra: str | None = None) -> None:
        """统一控制忙闲状态和输入框可用性。"""

        self.busy = busy
        self.status_extra = extra
        self.input_bar.disabled = busy
        self.thread_picker_search.disabled = busy
        self.sync_page()
        if not busy:
            if self.thread_picker.has_class("-open"):
                self.thread_picker_search.focus()
            else:
                self.input_bar.focus()

    def on_input_changed(self, event: Input.Changed) -> None:
        """处理输入框变更；用于实时过滤候选列表。"""

        if event.input.id == "thread-picker-search":
            self._refresh_thread_picker(event.value)
            return

        if event.input.id == "input-bar" and not self.busy:
            if self._suppress_command_picker_refresh:
                return
            self._refresh_command_picker(event.value)

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        """鼠标或回车选择内联候选项。"""

        if event.list_view.id == "thread-picker-list" and isinstance(event.item, ThreadListItem):
            self.switch_thread(event.item.entry.thread_id)
            return

        if event.list_view.id == "command-picker-list" and isinstance(event.item, CommandListItem):
            self._execute_command_suggestion(event.item.entry.command)
            return

        if event.list_view.id == "model-picker-list" and isinstance(event.item, ModelListItem):
            self.switch_model(event.item.entry.alias)

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

        if self.model_picker.has_class("-open"):
            if event.key == "up":
                self._move_model_picker_selection(-1)
                event.stop()
                return

            if event.key == "down":
                self._move_model_picker_selection(1)
                event.stop()
                return

        if not self.thread_picker.has_class("-open"):
            return

        if event.key == "up":
            self._move_thread_picker_selection(-1)
            event.stop()
            return

        if event.key == "down":
            self._move_thread_picker_selection(1)
            event.stop()

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        """处理输入提交。"""

        if event.input.id == "thread-picker-search":
            selected = self._current_thread_entry()
            if selected is None:
                self.append_info_block("没有匹配的线程")
                self.hide_thread_picker()
                self.sync_page()
                return
            self.switch_thread(selected.thread_id)
            return

        text = event.value.strip()
        if event.input.id == "input-bar" and self.model_picker.has_class("-open"):
            selected_model = self._current_model_entry()
            if selected_model is not None:
                self.input_bar.value = ""
                self.switch_model(selected_model.alias)
                return

        if not text:
            return

        if self.busy:
            self.append_info_block("当前还有任务在跑")
            return

        if event.input.id == "input-bar" and self.command_picker.has_class("-open"):
            selected_command = self._current_command_entry()
            if selected_command is not None:
                self._execute_command_suggestion(selected_command.command)
                return

        self.input_bar.value = ""
        self.hide_command_picker()

        if text.startswith("/"):
            self.run_worker(self.command_handler.run(text), exclusive=True, group="cli-command")
            return

        self.run_worker(self.conversation_handler.run(text), exclusive=True, group="task")


async def run_once(user_message: str) -> None:
    """命令行单次模式。"""

    console = Console()
    service = create_app_service()
    printed = False
    async for event in service.run_task_stream(
        TaskRequest(thread_id="cli:default", objective=user_message)
    ):
        if event.type == "assistant_delta":
            delta = event.payload.get("delta") or event.message or ""
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


__all__ = [
    "BananaTUI",
    "main",
    "run_once",
]
