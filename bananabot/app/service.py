"""应用服务层，负责把上层界面接到统一 runtime 入口。"""

from __future__ import annotations

import asyncio
import contextlib
from dataclasses import dataclass
from datetime import datetime
from typing import AsyncIterator

from ..infra import FileRuntimeStateStore
from ..infra.logging import write_debug_messages
from ..llm import LLMClient
from ..memory import (
    CompactService,
    FileWorkingMemoryStore,
    MemoryStore,
    ThreadStore,
    ThreadStoreManager,
)
from ..runtime import (
    AgentRunner,
    EventEnvelope,
    TaskRun,
    TaskRunStatus,
    ThreadRef,
    build_context,
)
from ..tools import ToolRegistry
from .contracts import (
    AgentEvent,
    TaskRequest,
    TaskResponse,
)

@dataclass(slots=True)
class _TaskExecutionContext:
    """当前这次任务执行的过渡上下文。"""

    request: TaskRequest
    thread: ThreadRef
    task_run: TaskRun
    thread_store: ThreadStore


class AppService:
    """顶层应用服务，供 CLI 和后续客户端复用。"""

    def __init__(
        self,
        config,
        llm: LLMClient,
        registry: ToolRegistry,
        thread_stores: ThreadStoreManager,
    ):
        """保存应用服务运行所需的核心依赖。"""

        self.config = config
        self.llm = llm
        self.registry = registry
        self.thread_stores = thread_stores
        self.project_memory_store = MemoryStore(config.workspace, config.global_dir)
        self.working_memory_store = FileWorkingMemoryStore(config.global_dir / "working-memory")
        self.runtime_state_store = FileRuntimeStateStore(config.runtime_state_dir)

    async def run_task(self, request: TaskRequest) -> TaskResponse:
        """执行一次任务请求并返回最终结果。"""

        final_output = ""
        finish_reason = "stop"
        final_status = TaskRunStatus.COMPLETED.value
        task_run_id = request.task_run_id or ""

        async for event in self.run_task_stream(request):
            task_run_id = event.task_run_id or task_run_id
            if event.type == "assistant_message":
                final_output = event.message or ""
            elif event.type == "done":
                finish_reason = event.payload.get("finish_reason", "stop")
                final_status = event.status

        return TaskResponse(
            thread_id=request.thread_id,
            task_run_id=task_run_id or request.task_run_id or request.thread_id,
            output=final_output or "[无回复内容]",
            finish_reason=finish_reason,
            status=final_status,
            metadata={"runtime_mode": "task_runtime_bridge"},
        )

    async def run_task_stream(self, request: TaskRequest) -> AsyncIterator[AgentEvent]:
        """执行一次任务请求，并持续产出 thread/task 风格事件。"""

        context = self._create_execution_context(request)

        queue: asyncio.Queue[AgentEvent] = asyncio.Queue()
        task_error: Exception | None = None

        def emit_runtime_event(event: EventEnvelope) -> None:
            """把 runtime 内部事件适配成应用层统一事件。"""

            queue.put_nowait(self._build_runtime_agent_event(context, event))

        async def run_runtime_task() -> None:
            """在后台执行 runtime 主循环，并把结果落到现有会话存储。"""

            nonlocal task_error
            try:
                self._persist_runtime_root(context)

                # 当前设计下，history 是完整历史日志，因此每轮真实消息都持续追加。
                context.thread_store.add("user", context.request.objective)
                context.thread_store.append_history(
                    [{"role": "user", "content": context.request.objective}]
                )

                messages = build_context(
                    workspace=self.config.workspace,
                    thread_store=context.thread_store,
                    thread=context.thread,
                    task_run=context.task_run,
                    messages=list(context.thread_store.messages),
                    memory_store=self.project_memory_store,
                    working_memory_store=self.working_memory_store,
                )
                write_debug_messages(context.thread_store, messages)

                # 记录运行前消息数量，便于只提取本轮新增的 assistant/tool 消息。
                msg_count_before = len(messages)

                runner = AgentRunner(
                    llm=self.llm,
                    registry=self.registry,
                    max_iterations=self.config.max_iterations,
                )
                response = await runner.run(
                    messages,
                    event_callback=emit_runtime_event,
                    thread_id=context.thread.id,
                    task_run_id=context.task_run.id,
                    thread_title=context.thread.title,
                    thread_metadata=dict(context.thread.metadata),
                    task_metadata=dict(context.task_run.metadata),
                    state_store=self.runtime_state_store,
                )

                # runner 会直接把新增消息写进 `messages`，这里负责把它们落盘到会话。
                for msg in messages[msg_count_before:]:
                    if msg["role"] in ("assistant", "tool"):
                        context.thread_store.add_message(msg)
                        context.thread_store.append_history([msg])

                self._update_working_memory(
                    context,
                    response_output=response.content,
                    new_messages=messages[msg_count_before:],
                )

                compact_svc = CompactService(
                    thread_store=context.thread_store,
                    llm=self.llm,
                    config=self.config,
                )
                await compact_svc.run_if_needed()

                queue.put_nowait(
                    self._build_agent_event(
                        event_type="done",
                        status=TaskRunStatus.COMPLETED.value,
                        thread_id=context.thread.id,
                        task_run_id=context.task_run.id,
                        payload={
                            "finish_reason": response.finish_reason,
                            "task_run_id": context.task_run.id,
                        },
                    )
                )
            except Exception as exc:  # pragma: no cover
                task_error = exc
                self._update_working_memory(
                    context,
                    response_output=None,
                    new_messages=[],
                    error=str(exc),
                )
                queue.put_nowait(
                    self._build_agent_event(
                        event_type="error",
                        status=TaskRunStatus.FAILED.value,
                        thread_id=context.thread.id,
                        task_run_id=context.task_run.id,
                        message=str(exc),
                    )
                )
                queue.put_nowait(
                    self._build_agent_event(
                        event_type="done",
                        status=TaskRunStatus.FAILED.value,
                        thread_id=context.thread.id,
                        task_run_id=context.task_run.id,
                        payload={"finish_reason": "error", "task_run_id": context.task_run.id},
                    )
                )

        task = asyncio.create_task(run_runtime_task())
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

    def _create_execution_context(self, request: TaskRequest) -> _TaskExecutionContext:
        """为一次请求创建 thread/task 过渡上下文。"""

        metadata = dict(request.metadata or {})
        thread = ThreadRef(
            id=request.thread_id,
            title=metadata.get("thread_title"),
            metadata=metadata,
        )
        task_run = TaskRun(thread_id=thread.id, objective=request.objective, metadata=dict(metadata))
        if request.task_run_id:
            task_run.id = request.task_run_id
        thread_store = self.thread_stores.get_or_create_thread(thread.id)
        return _TaskExecutionContext(
            request=request,
            thread=thread,
            task_run=task_run,
            thread_store=thread_store,
        )

    def _persist_runtime_root(self, context: _TaskExecutionContext) -> None:
        """在 runtime 启动前预写 thread/task 根状态。"""

        try:
            self.runtime_state_store.save_thread(context.thread)
            self.runtime_state_store.save_task_run(context.task_run)
        except Exception:
            return

    def _update_working_memory(
        self,
        context: _TaskExecutionContext,
        *,
        response_output: str | None,
        new_messages: list[dict],
        error: str | None = None,
    ) -> None:
        """把本轮执行结果回写到 thread/task working memory。"""

        thread_memory = self.working_memory_store.load_or_create(
            thread_id=context.thread.id,
            objective=context.request.objective,
        )
        task_memory = self.working_memory_store.load_or_create(
            thread_id=context.thread.id,
            task_run_id=context.task_run.id,
            objective=context.request.objective,
        )

        for memory in (thread_memory, task_memory):
            memory.objective = context.request.objective
            memory.user_intent = context.request.objective
            memory.metadata["last_task_run_id"] = context.task_run.id
            if response_output:
                memory.summary = response_output
            if error:
                memory.metadata["last_error"] = error

        tool_observations: list[str] = []
        for message in new_messages:
            if message.get("role") != "tool":
                continue
            content = (message.get("content") or "").strip()
            if content:
                tool_observations.append(content[:240])

        if tool_observations:
            thread_memory.tool_observations = tool_observations[-8:]
            task_memory.tool_observations = tool_observations[-8:]

        if response_output:
            response_line = response_output.strip()
            if response_line:
                thread_memory.recent_facts = [response_line[:240]]
                task_memory.recent_facts = [response_line[:240]]

        self.working_memory_store.save(thread_memory)
        self.working_memory_store.save(task_memory)

    def _build_runtime_agent_event(
        self,
        context: _TaskExecutionContext,
        event: EventEnvelope,
    ) -> AgentEvent:
        """把 runtime 事件适配成新的 thread/task 风格事件。"""

        return self._build_agent_event(
            event_type=event.type,
            status=event.status,
            thread_id=event.thread_id or context.thread.id,
            task_run_id=event.task_run_id or context.task_run.id,
            turn_id=event.turn_id,
            step_id=event.step_id,
            message=event.message,
            payload=dict(event.payload),
            event_id=event.event_id,
            timestamp=event.timestamp,
        )

    def _build_agent_event(
        self,
        *,
        event_type: str,
        status: str,
        thread_id: str,
        task_run_id: str | None = None,
        turn_id: str | None = None,
        step_id: str | None = None,
        message: str | None = None,
        payload: dict | None = None,
        event_id: str | None = None,
        timestamp: datetime | None = None,
    ) -> AgentEvent:
        """统一构建带 thread/task/turn/step 标识的应用事件。"""

        return AgentEvent(
            type=event_type,
            thread_id=thread_id,
            task_run_id=task_run_id,
            turn_id=turn_id,
            step_id=step_id,
            status=status,
            message=message,
            payload=payload or {},
            event_id=event_id,
            timestamp=timestamp,
        )

    def create_thread(self, prefix: str = "cli") -> ThreadStore:
        """创建并返回一个带时间戳的新 thread store。"""

        thread_id = f"{prefix}:{datetime.now().strftime('%Y%m%d%H%M%S')}"
        return self.thread_stores.get_or_create_thread(thread_id)

    def get_thread(self, thread_id: str) -> ThreadStore:
        """获取已有 thread store，不存在则创建。"""

        return self.thread_stores.get_or_create_thread(thread_id)

    def list_threads(self) -> list[str]:
        """列出当前所有 thread。"""

        return self.thread_stores.list_threads()

    def clear_thread(self, thread_id: str) -> None:
        """清空指定 thread 的当前消息窗口。"""

        thread = self.thread_stores.get_or_create_thread(thread_id)
        thread.clear()

    async def compact_thread(self, thread_id: str, force: bool = True) -> dict:
        """对指定 thread 执行 compact，并返回状态摘要。"""

        thread_store = self.thread_stores.get_or_create_thread(thread_id)
        compact_svc = CompactService(thread_store=thread_store, llm=self.llm, config=self.config)
        did_compact = await compact_svc.run_if_needed(force=force)
        return {
            "did_compact": did_compact,
            "summary_count": thread_store.get_summary_count(),
            "has_memory": thread_store.has_memory(),
        }

    def get_thread_status(self, thread_id: str) -> dict:
        """返回 thread 状态，供界面展示。

        当前返回的是面向 CLI/TUI 的状态快照。
        """

        thread_store = self.thread_stores.get_or_create_thread(thread_id)
        history_lines = 0
        if thread_store.history_path and thread_store.history_path.exists():
            with open(thread_store.history_path, encoding="utf-8") as handle:
                history_lines = sum(1 for _ in handle)

        if hasattr(self.llm, "get_current_profile"):
            current_profile = self.llm.get_current_profile()
            model_name = current_profile.model
            model_alias = self.llm.get_model_alias()
        else:
            model_name = self.config.model
            model_alias = self.config.model

        return {
            "thread_id": thread_store.key,
            "runtime_mode": "task_runtime_bridge",
            "message_count": len(thread_store.messages),
            "workspace": str(self.config.workspace),
            "model": model_name,
            "model_alias": model_alias,
            "paths": {
                "window": str(thread_store.session_path) if thread_store.session_path else None,
                "history": str(thread_store.history_path) if thread_store.history_path else None,
                "summary": str(thread_store.summary_path) if thread_store.summary_path else None,
                "memory": str(thread_store.memory_path) if thread_store.memory_path else None,
            },
            "history_count": history_lines,
            "summary_count": thread_store.get_summary_count(),
            "has_memory": thread_store.has_memory(),
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

    def list_models(self) -> list[dict]:
        """列出当前可切换的模型。"""

        if not hasattr(self.llm, "list_models"):
            return [
                {
                    "alias": self.config.model,
                    "model": self.config.model,
                    "provider": "test",
                    "description": self.config.model,
                    "capabilities": {
                        "stream": True,
                        "tools": True,
                        "reasoning": False,
                    },
                    "current": True,
                }
            ]

        current = self.llm.get_model_alias()
        models = []
        for profile in self.llm.list_models():
            models.append(
                {
                    "alias": profile.alias,
                    "model": profile.model,
                    "provider": profile.provider,
                    "description": profile.label,
                    "capabilities": {
                        "stream": profile.capabilities.supports_stream,
                        "tools": profile.capabilities.supports_tools,
                        "reasoning": profile.capabilities.supports_reasoning,
                    },
                    "current": profile.alias == current,
                }
            )
        return models

    def switch_model(self, alias_or_model: str) -> dict:
        """切换当前模型，并同步配置快照。"""

        if not hasattr(self.llm, "set_model"):
            raise RuntimeError("当前 LLM 实现不支持模型切换")
        profile = self.llm.set_model(alias_or_model)
        self.config.model_alias = profile.alias
        self.config.model = profile.model
        self.config.base_url = profile.base_url
        self.config.api_key = profile.api_key
        return {
            "alias": profile.alias,
            "model": profile.model,
            "provider": profile.provider,
            "description": profile.label,
            "capabilities": {
                "stream": profile.capabilities.supports_stream,
                "tools": profile.capabilities.supports_tools,
                "reasoning": profile.capabilities.supports_reasoning,
            },
        }
