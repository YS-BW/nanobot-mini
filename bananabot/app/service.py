"""应用服务层，负责聊天流程与会话命令编排。

这是当前项目最重要的协调层之一。

它的职责不是实现模型推理、不是直接操作工具、也不是管理底层存储，
而是把这些能力按一次“完整对话请求”的流程串起来：

1. 接收统一的 `ChatRequest`
2. 找到或创建会话
3. 组装上下文
4. 驱动运行时主循环
5. 把新增消息写回 session / history
6. 在必要时触发 compact
7. 向上层返回统一的响应或事件

CLI、未来的 Web 端、桌面端都应该优先依赖这一层，而不是直接碰底层对象。
"""

import asyncio
import contextlib
from datetime import datetime
from typing import AsyncIterator

from ..infra.logging import write_debug_messages
from ..llm import LLMClient
from ..memory import CompactService, MemoryStore, Session, SessionManager
from ..runtime import AgentRunner, RuntimeEvent, build_context
from ..tools import ToolRegistry
from .contracts import AgentEvent, ChatRequest, ChatResponse


class AppService:
    """顶层应用服务，供 CLI 和后续客户端复用。

    可以把它理解成“项目的统一对话入口”。
    对外暴露的是稳定接口，对内再去协调 runtime、memory、llm、tools。
    """

    def __init__(self, config, llm: LLMClient, registry: ToolRegistry, sessions: SessionManager):
        """保存应用服务运行所需的核心依赖。"""
        self.config = config
        self.llm = llm
        self.registry = registry
        self.sessions = sessions

    async def chat(self, request: ChatRequest) -> ChatResponse:
        """执行一次聊天请求并返回最终回复。

        这是“只关心最终结果”的便捷接口。
        内部仍然会走 `chat_stream()`，只是把中间事件消费掉，最后收集最终回复。
        """

        final_message = ""
        finish_reason = "stop"
        async for event in self.chat_stream(request):
            if event.type == "assistant_message":
                final_message = event.message or ""
            elif event.type == "done":
                finish_reason = (event.data or {}).get("finish_reason", "stop")

        return ChatResponse(
            session_id=request.session_id,
            message=final_message or "[无回复内容]",
            finish_reason=finish_reason,
        )

    async def chat_stream(self, request: ChatRequest) -> AsyncIterator[AgentEvent]:
        """执行一次聊天请求，并持续产出统一事件。

        这是当前应用层最核心的方法。

        它做两件事：
        - 驱动一次完整的对话执行
        - 把运行时中间状态转成统一事件，供上层界面实时消费

        CLI 现在就是靠这个接口显示进度框；以后 Web 端和桌面端也应该走它。
        """

        queue: asyncio.Queue[AgentEvent] = asyncio.Queue()
        task_error: Exception | None = None

        def emit_runtime_event(event: RuntimeEvent) -> None:
            """把运行时内部事件转换成应用层统一事件。"""
            queue.put_nowait(
                AgentEvent(
                    type=event.type,
                    session_id=request.session_id,
                    message=event.message,
                    data=event.data,
                )
            )

        async def run_chat() -> None:
            """在后台执行完整对话流程，并把事件推到队列里。"""
            nonlocal task_error
            try:
                session = self.sessions.get_or_create(request.session_id)

                # 当前设计下，history 是完整历史日志，因此每轮真实消息都持续追加。
                session.add("user", request.user_input)
                session.append_history([{"role": "user", "content": request.user_input}])

                messages = build_context(session=session, workspace=self.config.workspace)
                write_debug_messages(session, messages)

                # 记录运行前消息数量，便于只提取本轮新增的 assistant/tool 消息。
                msg_count_before = len(messages)

                runner = AgentRunner(
                    llm=self.llm,
                    registry=self.registry,
                    max_iterations=self.config.max_iterations,
                )
                response = await runner.run(messages, event_callback=emit_runtime_event)

                # runner 会直接把新增消息写进 `messages`，这里负责把它们落盘到会话。
                for msg in messages[msg_count_before:]:
                    if msg["role"] in ("assistant", "tool"):
                        content = msg.get("content", "")
                        session.add(msg["role"], content)
                        session.append_history([{"role": msg["role"], "content": content}])

                compact_svc = CompactService(session=session, llm=self.llm, config=self.config)
                await compact_svc.run_if_needed()

                # 运行结束后，再统一产出一个最终回复事件和 done 事件。
                queue.put_nowait(
                    AgentEvent(
                        type="assistant_message",
                        session_id=request.session_id,
                        message=response.content or "[无回复内容]",
                    )
                )
                queue.put_nowait(
                    AgentEvent(
                        type="done",
                        session_id=request.session_id,
                        data={"finish_reason": response.finish_reason},
                    )
                )
            except Exception as exc:  # pragma: no cover
                task_error = exc
                queue.put_nowait(
                    AgentEvent(
                        type="error",
                        session_id=request.session_id,
                        message=str(exc),
                    )
                )
                queue.put_nowait(
                    AgentEvent(
                        type="done",
                        session_id=request.session_id,
                        data={"finish_reason": "error"},
                    )
                )

        task = asyncio.create_task(run_chat())
        try:
            while True:
                event = await queue.get()
                yield event
                if event.type == "done":
                    break
            await task
            if task_error is not None:
                raise task_error
        finally:
            if not task.done():
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task

    def create_session(self, prefix: str = "cli") -> Session:
        """创建并返回一个带时间戳的新会话。"""

        session_id = f"{prefix}:{datetime.now().strftime('%Y%m%d%H%M%S')}"
        return self.sessions.get_or_create(session_id)

    def get_session(self, session_id: str) -> Session:
        """获取已有会话，不存在则创建。"""

        return self.sessions.get_or_create(session_id)

    def list_sessions(self) -> list[str]:
        """列出当前所有会话。"""

        return self.sessions.list_sessions()

    def clear_session(self, session_id: str) -> None:
        """清空会话当前消息窗口。"""

        session = self.sessions.get_or_create(session_id)
        session.clear()

    async def compact_session(self, session_id: str, force: bool = True) -> dict:
        """对指定会话执行 compact，并返回状态摘要。

        这里返回的是界面层最关心的几个字段，而不是把整个 `Session` 暴露出去。
        这样可以避免上层界面越来越依赖底层存储细节。
        """

        session = self.sessions.get_or_create(session_id)
        compact_svc = CompactService(session=session, llm=self.llm, config=self.config)
        did_compact = await compact_svc.run_if_needed(force=force)
        return {
            "did_compact": did_compact,
            "summary_count": session.get_summary_count(),
            "has_memory": session.has_memory(),
        }

    def get_status(self, session_id: str) -> dict:
        """返回会话状态，供界面展示。

        当前返回的是面向 CLI 的状态快照，后续如果 Web 或桌面端需要更多字段，
        也应该优先在这里扩展，而不是让它们自己去读 session 文件。
        """

        session = self.sessions.get_or_create(session_id)
        history_lines = 0
        if session.history_path and session.history_path.exists():
            with open(session.history_path, encoding="utf-8") as handle:
                history_lines = sum(1 for _ in handle)

        return {
            "session_id": session.key,
            "message_count": len(session.messages),
            "workspace": str(self.config.workspace),
            "model": self.config.model,
            "paths": {
                "session": str(session.session_path) if session.session_path else None,
                "history": str(session.history_path) if session.history_path else None,
                "summary": str(session.summary_path) if session.summary_path else None,
                "memory": str(session.memory_path) if session.memory_path else None,
            },
            "history_count": history_lines,
            "summary_count": session.get_summary_count(),
            "has_memory": session.has_memory(),
        }

    def get_banana_info(self) -> dict:
        """返回全局和项目指令文件的预览信息。"""

        global_banana = self.config.global_dir / "BANANA.md"
        project_banana = MemoryStore.find_banana_md(self.config.workspace)
        return {
            "global_path": str(global_banana),
            "global_preview": (
                global_banana.read_text(encoding="utf-8")[:500]
                if global_banana.exists()
                else None
            ),
            "project_path": str(project_banana) if project_banana else None,
            "project_preview": (
                project_banana.read_text(encoding="utf-8")[:500]
                if project_banana and project_banana.exists()
                else None
            ),
        }
