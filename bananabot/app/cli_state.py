"""TUI 纸面状态。

这个对象只管理纸面正文和 thinking 区域的临时状态，
不碰 Textual 组件，也不直接调用 service。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .cli_render import render_prefixed_block, render_thinking_box, wrap_for_box


@dataclass
class PaperState:
    """一张滚动纸面的正文状态。"""

    body_blocks: list[str] = field(default_factory=list)
    thinking_slot_index: int | None = None
    live_assistant_index: int | None = None
    reasoning_buffer: str = ""
    round_tools: list[str] = field(default_factory=list)

    def rebuild_from_thread_messages(self, messages: list[dict]) -> None:
        """根据持久化消息重建正文。"""

        blocks: list[str] = []
        for message in messages:
            if message["role"] == "user":
                blocks.append(render_prefixed_block("❯", message.get("content", "")))
            elif message["role"] == "assistant":
                blocks.append(render_prefixed_block("⏺", message.get("content", "")))
        self.body_blocks = blocks
        self.reset_round_state()

    def render_document(self, welcome_block: str) -> str:
        """把欢迎区和正文拼成最终纸面。"""

        parts = [welcome_block]
        if self.body_blocks:
            parts.append("\n\n".join(block for block in self.body_blocks if block).rstrip())
        return "\n\n".join(part for part in parts if part).rstrip()

    def append_info_block(self, text: str) -> None:
        """追加系统/命令输出块。"""

        self.body_blocks.append(render_prefixed_block("⏺", text))

    def append_user_block(self, text: str) -> None:
        """追加用户输入块。"""

        self.body_blocks.append(render_prefixed_block("❯", text))

    def ensure_thinking_slot(self) -> None:
        """确保当前轮存在 thinking 占位槽。"""

        if self.thinking_slot_index is None:
            self.body_blocks.append("")
            self.thinking_slot_index = len(self.body_blocks) - 1

    def append_reasoning_chunk(self, chunk: str) -> None:
        """把模型思考增量拼进 thinking 框。"""

        if not chunk:
            return
        self.ensure_thinking_slot()
        self.reasoning_buffer += chunk
        self._replace_or_append(
            self.thinking_slot_index,
            self.render_live_thinking_box(),
        )

    def record_tool_call(self, tool_name: str) -> None:
        """记录本轮调用过的工具，并刷新 thinking 框。"""

        if not tool_name:
            return
        if tool_name not in self.round_tools:
            self.round_tools.append(tool_name)
        self.ensure_thinking_slot()
        self._replace_or_append(
            self.thinking_slot_index,
            self.render_live_thinking_box(),
        )

    def finalize_thinking(self) -> None:
        """根据本轮结果收口 thinking 展示。"""

        if self.thinking_slot_index is None:
            return

        if self.round_tools:
            summary_lines = ["tools"] + self.round_tools[:4]
            self._replace_or_append(
                self.thinking_slot_index,
                render_thinking_box("thinking", summary_lines, max_height=5),
            )
        else:
            self._replace_or_append(self.thinking_slot_index, "**Thinked**")

        self.reasoning_buffer = ""

    def append_assistant_delta(self, delta: str) -> None:
        """把 assistant 正文增量写进正文。"""

        if self.live_assistant_index is None:
            self.body_blocks.append(render_prefixed_block("⏺", delta))
            self.live_assistant_index = len(self.body_blocks) - 1
            return

        current_text = self.body_blocks[self.live_assistant_index]
        prefix = "⏺ "
        content = current_text[len(prefix):] if current_text.startswith(prefix) else current_text
        content = content.replace("\n  ", "\n")
        content += delta
        self._replace_or_append(
            self.live_assistant_index,
            render_prefixed_block("⏺", content),
        )

    def finalize_assistant_block(self, text: str) -> None:
        """在无增量正文时，用最终回复补齐 assistant 块。"""

        if self.live_assistant_index is None:
            self.body_blocks.append(render_prefixed_block("⏺", text))
            self.live_assistant_index = len(self.body_blocks) - 1

    def render_live_thinking_box(self) -> str:
        """渲染执行中的 thinking 框。"""

        lines = wrap_for_box(self.reasoning_buffer)
        lines.extend([f"tool: {tool}" for tool in self.round_tools])
        return render_thinking_box("thinking", lines, max_height=5, min_height=5)

    def reset_round_state(self) -> None:
        """清掉当前轮的临时过程状态。"""

        self.thinking_slot_index = None
        self.live_assistant_index = None
        self.reasoning_buffer = ""
        self.round_tools = []

    def _replace_or_append(self, index: int | None, text: str) -> None:
        """替换指定块；如果索引不存在则追加。"""

        if index is None or index >= len(self.body_blocks):
            self.body_blocks.append(text)
            return
        self.body_blocks[index] = text
