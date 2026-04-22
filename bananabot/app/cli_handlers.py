"""TUI 行为处理器。

把命令执行和事件流消费从 Textual App 类里拆出来，
避免 `cli.py` 同时承担界面和业务编排两层职责。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .cli_render import banana_lines, status_lines
from .contracts import TaskRequest

if TYPE_CHECKING:
    from .cli import BananaTUI


class CLICommandHandler:
    """处理 TUI 内置命令。"""

    def __init__(self, app: "BananaTUI"):
        self.app = app

    async def run(self, command: str) -> None:
        """执行一条内置命令。"""

        command = command.strip()
        lower = command.lower()
        self.app.append_user_block(command)

        if lower == "/help":
            self.app.append_info_block(
                "\n".join(
                    [
                        "可用命令:",
                        "  /model            切换当前模型",
                        "  /new              开启新线程",
                        "  /threads          打开线程切换列表",
                        "  /clear            清空当前线程窗口",
                        "  /status           显示当前状态",
                        "  /compact          压缩当前线程",
                        "  /banana           查看全局/项目指令",
                        "  /help             显示帮助",
                        "  /exit             退出程序",
                    ]
                )
            )
            return

        if lower == "/exit":
            self.app.exit()
            return

        if lower == "/model":
            self.app.show_model_picker()
            return

        if lower.startswith("/model "):
            target = command.split(None, 1)[1].strip()
            try:
                self.app.switch_model(target)
            except Exception as exc:  # pragma: no cover
                self.app.append_info_block(f"模型切换失败: {exc}")
            return

        if lower == "/new":
            self.app.thread_store = self.app.service.create_thread()
            self.app.rebuild_body_from_thread()
            self.app.append_info_block(f"已开启新线程 {self.app.thread_store.key}")
            self.app.sync_page()
            return

        if lower == "/threads":
            self.app.show_thread_picker()
            return

        if lower == "/clear":
            self.app.service.clear_thread(self.app.thread_store.key)
            self.app.rebuild_body_from_thread()
            self.app.append_info_block(f"已清空线程 {self.app.thread_store.key} 的当前窗口")
            self.app.sync_page()
            return

        if lower == "/status":
            self.app.append_info_block(
                "\n".join(status_lines(self.app.service.get_thread_status(self.app.thread_store.key)))
            )
            return

        if lower == "/banana":
            self.app.append_info_block("\n".join(banana_lines(self.app.service.get_banana_info())))
            return

        if lower == "/compact":
            self.app.set_busy(True, extra="compact 中")
            try:
                result = await self.app.service.compact_thread(self.app.thread_store.key, force=True)
                self.app.rebuild_body_from_thread()
                if not result["did_compact"]:
                    self.app.append_info_block("当前无需压缩")
                elif result["has_memory"]:
                    self.app.append_info_block("compact 完成，内容已整合到 MEMORY.md")
                else:
                    self.app.append_info_block(
                        f"compact 完成，摘要已保存（当前 {result['summary_count']} 条）"
                    )
                self.app.sync_page()
            except Exception as exc:  # pragma: no cover
                self.app.append_info_block(f"compact 失败: {exc}")
            finally:
                self.app.set_busy(False)
            return

        self.app.append_info_block(f"未知命令: {command}")


class CLIConversationHandler:
    """处理一次对话请求，并把事件流投影到纸面。"""

    def __init__(self, app: "BananaTUI"):
        self.app = app

    async def run(self, user_message: str) -> None:
        """执行一次任务，并把事件流实时写入纸面正文。"""

        self.app.paper_state.reset_round_state()
        self.app.append_user_block(user_message)
        self.app.ensure_thinking_slot()
        self.app.set_busy(True, extra="对话中")

        try:
            async for event in self.app.service.run_task_stream(
                TaskRequest(thread_id=self.app.thread_store.key, objective=user_message)
            ):
                if event.type == "assistant_thinking":
                    continue
                if event.type == "assistant_reasoning_delta":
                    delta = event.payload.get("delta") or event.message or ""
                    self.app.append_reasoning_chunk(delta)
                elif event.type == "tool_call_started":
                    self.app.record_tool_call(event.payload.get("tool_name") or "")
                elif event.type == "assistant_delta":
                    delta = event.payload.get("delta") or event.message or ""
                    if delta:
                        self.app.append_assistant_delta(delta)
                elif event.type == "error":
                    self.app.finalize_thinking()
                    if event.message:
                        self.app.append_info_block(event.message)
                elif event.type == "assistant_message":
                    self.app.finalize_thinking()
                    self.app.finalize_assistant_block(event.message or "[无回复内容]")
                elif event.type == "done":
                    self.app.finalize_thinking()

            self.app.status_extra = "已完成"
            self.app.sync_page()
        except Exception as exc:  # pragma: no cover
            self.app.finalize_thinking()
            self.app.append_info_block(f"对话执行失败: {exc}")
        finally:
            self.app.set_busy(False)
            self.app.paper_state.reset_round_state()
            self.app.status_extra = None
            self.app.sync_page()
