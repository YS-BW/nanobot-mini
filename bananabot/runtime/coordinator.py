"""运行时协调器。

当前 runtime 不再拆成“状态机 + 协调器”两层。
这个文件直接负责：

1. 维护 thread / task_run / turn / step 的运行中状态
2. 产出统一 `EventEnvelope`
3. 把状态和事件落到运行时仓库
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import uuid4

from .events import EventEnvelope
from .models import Step, StepKind, StepStatus, TaskRun, TaskRunStatus, ThreadRef, Turn, TurnStatus

EventCallback = Callable[[EventEnvelope], None] | None


def _utc_now() -> datetime:
    """统一生成当前 UTC 时间。"""

    return datetime.utcnow()


def _new_thread_id() -> str:
    """生成 thread ID。"""

    return f"thread_{uuid4().hex}"


def _new_task_run_id() -> str:
    """生成 task run ID。"""

    return f"task_{uuid4().hex}"


@dataclass(slots=True)
class _RuntimeState:
    """当前一次运行内的最小状态快照。"""

    current_turn: Turn | None = None
    turns: list[Turn] = field(default_factory=list)
    steps_by_turn: dict[str, list[Step]] = field(default_factory=dict)


class RuntimeCoordinator:
    """统一管理运行时状态推进和事件发射。"""

    def __init__(
        self,
        *,
        thread: ThreadRef,
        task_run: TaskRun,
        event_callback: EventCallback = None,
        state_store: Any | None = None,
    ):
        self.thread = thread
        self.task_run = task_run
        self.event_callback = event_callback
        self.state_store = state_store
        self.state = _RuntimeState()
        self._persist_root_state()

    @classmethod
    def from_messages(
        cls,
        messages: list[dict],
        event_callback: EventCallback = None,
        *,
        thread_id: str | None = None,
        task_run_id: str | None = None,
        thread_title: str | None = None,
        thread_metadata: dict[str, Any] | None = None,
        task_metadata: dict[str, Any] | None = None,
        state_store: Any | None = None,
    ) -> RuntimeCoordinator:
        """根据当前消息窗口推导 thread/task，并创建协调器。"""

        objective = cls._derive_objective(messages)
        thread = ThreadRef(
            id=thread_id or _new_thread_id(),
            title=thread_title or objective[:48] or "bananabot thread",
            metadata=dict(thread_metadata or {}),
        )
        task_run = TaskRun(
            id=task_run_id or _new_task_run_id(),
            thread_id=thread.id,
            objective=objective or "bananabot task",
            metadata=dict(task_metadata or {}),
        )
        return cls(
            thread=thread,
            task_run=task_run,
            event_callback=event_callback,
            state_store=state_store,
        )

    def start_task_run(self, metadata: dict[str, Any] | None = None) -> TaskRun:
        """启动 task run，并发出结构化开始事件。"""

        if self.task_run.status not in {TaskRunStatus.PENDING, TaskRunStatus.RUNNING}:
            raise RuntimeError(f"Task run cannot be started from status: {self.task_run.status}")
        self.task_run.status = TaskRunStatus.RUNNING
        self._merge_metadata(self.task_run.metadata, metadata)
        self._touch_task()
        self._persist_root_state()
        self.emit_event(
            "task_run_started",
            status=self.task_run.status,
            message=self.task_run.objective,
            payload={"objective": self.task_run.objective, "metadata": dict(self.task_run.metadata)},
        )
        return self.task_run

    def complete_task_run(self, payload: dict[str, Any] | None = None) -> TaskRun:
        """结束 task run，并发出完成事件。"""

        self.task_run.status = TaskRunStatus.COMPLETED
        self._merge_metadata(self.task_run.metadata, payload)
        self.state.current_turn = None
        self._touch_task()
        self._persist_root_state()
        self.emit_event(
            "task_run_completed",
            status=self.task_run.status,
            payload={"objective": self.task_run.objective, "metadata": dict(self.task_run.metadata)},
        )
        return self.task_run

    def fail_task_run(self, error: str, payload: dict[str, Any] | None = None) -> TaskRun:
        """结束失败 task run，并发出失败事件。"""

        self.task_run.status = TaskRunStatus.FAILED
        self._merge_metadata(self.task_run.metadata, payload)
        self.task_run.metadata["error"] = error
        self.state.current_turn = None
        self._touch_task()
        self._persist_root_state()
        self.emit_event(
            "task_run_failed",
            status=self.task_run.status,
            message=error,
            payload={"objective": self.task_run.objective, "metadata": dict(self.task_run.metadata)},
        )
        return self.task_run

    def start_turn(self, payload: dict[str, Any] | None = None) -> Turn:
        """开始一个新 turn。"""

        if self.state.current_turn and self.state.current_turn.status == TurnStatus.RUNNING:
            raise RuntimeError("Cannot start a new turn while another turn is running")
        if self.task_run.status == TaskRunStatus.PENDING:
            self.start_task_run()
        if self.task_run.status != TaskRunStatus.RUNNING:
            raise RuntimeError(f"Cannot start turn when task run status is {self.task_run.status}")

        turn = Turn(
            task_run_id=self.task_run.id,
            sequence=len(self.state.turns) + 1,
            status=TurnStatus.RUNNING,
        )
        if payload:
            self.task_run.metadata.setdefault("turn_context", {})[turn.id] = dict(payload)
        self.state.turns.append(turn)
        self.state.current_turn = turn
        self.state.steps_by_turn.setdefault(turn.id, [])
        self._touch_turn(turn)
        self._touch_task()
        self._persist_turn(turn)
        self._persist_root_state()
        self.emit_event(
            "turn_started",
            status=turn.status,
            turn=turn,
            payload={"sequence": turn.sequence},
        )
        return turn

    def complete_turn(self, turn: Turn, payload: dict[str, Any] | None = None) -> Turn:
        """完成一个 turn。"""

        turn = self._find_turn(turn.id)
        turn.status = TurnStatus.COMPLETED
        if payload:
            self.task_run.metadata.setdefault("turn_results", {}).setdefault(turn.id, {}).update(payload)
        self._touch_turn(turn)
        if self.state.current_turn and self.state.current_turn.id == turn.id:
            self.state.current_turn = None
        self._touch_task()
        self._persist_turn(turn)
        self._persist_root_state()
        self.emit_event(
            "turn_completed",
            status=turn.status,
            turn=turn,
            payload={"sequence": turn.sequence},
        )
        return turn

    def fail_turn(self, turn: Turn, error: str, payload: dict[str, Any] | None = None) -> Turn:
        """标记 turn 失败。"""

        turn = self._find_turn(turn.id)
        turn.status = TurnStatus.FAILED
        failure = dict(payload or {})
        failure["error"] = error
        self.task_run.metadata.setdefault("turn_results", {}).setdefault(turn.id, {}).update(failure)
        self._touch_turn(turn)
        if self.state.current_turn and self.state.current_turn.id == turn.id:
            self.state.current_turn = None
        self._touch_task()
        self._persist_turn(turn)
        self._persist_root_state()
        self.emit_event(
            "turn_failed",
            status=turn.status,
            message=error,
            turn=turn,
            payload={"sequence": turn.sequence},
        )
        return turn

    def start_step(
        self,
        turn: Turn,
        kind: StepKind,
        *,
        event_type: str | None = None,
        message: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> Step:
        """创建并启动 step，同时发出步骤开始事件。"""

        turn = self._find_turn(turn.id)
        if turn.status != TurnStatus.RUNNING:
            raise RuntimeError(f"Cannot create step under turn status: {turn.status}")

        steps = self.state.steps_by_turn.setdefault(turn.id, [])
        step = Step(
            task_run_id=self.task_run.id,
            turn_id=turn.id,
            kind=kind,
            sequence=len(steps) + 1,
            status=StepStatus.RUNNING,
            payload=dict(payload or {}),
        )
        steps.append(step)
        self._touch_step(step)
        self._touch_turn(turn)
        self._touch_task()
        self._persist_turn(turn)
        self._persist_step(step)
        self._persist_root_state()
        self.emit_event(
            event_type or f"step_{kind}_started",
            status=step.status,
            message=message,
            turn=turn,
            step=step,
            payload=self._with_step_payload(step, payload),
        )
        return step

    def complete_step(
        self,
        step: Step,
        *,
        event_type: str | None = None,
        message: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> Step:
        """完成 step，并发出步骤完成事件。"""

        step = self._find_step(step.id)
        step.status = StepStatus.COMPLETED
        if payload:
            step.payload.update(payload)
        self._touch_step(step)
        self._touch_task()
        turn = self._turn_for_step(step)
        self._persist_turn(turn)
        self._persist_step(step)
        self._persist_root_state()
        self.emit_event(
            event_type or f"step_{step.kind}_completed",
            status=step.status,
            message=message,
            turn=turn,
            step=step,
            payload=self._with_step_payload(step, payload),
        )
        return step

    def fail_step(
        self,
        step: Step,
        *,
        error: str,
        message: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> Step:
        """将 step 标记为失败，并发出失败事件。"""

        step = self._find_step(step.id)
        step.status = StepStatus.FAILED
        if payload:
            step.payload.update(payload)
        step.payload["error"] = error
        self._touch_step(step)
        self._touch_task()
        turn = self._turn_for_step(step)
        self._persist_turn(turn)
        self._persist_step(step)
        self._persist_root_state()
        event_payload = self._with_step_payload(step, payload)
        event_payload["error"] = error
        self.emit_event(
            f"step_{step.kind}_failed",
            status=step.status,
            message=message or error,
            turn=turn,
            step=step,
            payload=event_payload,
        )
        return step

    def emit_event(
        self,
        event_type: str,
        *,
        status: str = "running",
        message: str | None = None,
        payload: dict[str, Any] | None = None,
        turn: Turn | None = None,
        step: Step | None = None,
    ) -> None:
        """向外发出统一运行时事件。"""

        event = EventEnvelope(
            type=event_type,
            status=status,
            message=message,
            payload=payload or {},
            thread_id=self.thread.id,
            task_run_id=self.task_run.id,
            turn_id=turn.id if turn else None,
            step_id=step.id if step else None,
        )
        self._persist_event(event)
        if self.event_callback:
            self.event_callback(event)

    def _find_turn(self, turn_id: str) -> Turn:
        """按 ID 查找 turn。"""

        for turn in self.state.turns:
            if turn.id == turn_id:
                return turn
        raise KeyError(f"Unknown turn id: {turn_id}")

    def _find_step(self, step_id: str) -> Step:
        """按 ID 查找 step。"""

        for steps in self.state.steps_by_turn.values():
            for step in steps:
                if step.id == step_id:
                    return step
        raise KeyError(f"Unknown step id: {step_id}")

    def _turn_for_step(self, step: Step) -> Turn:
        """按 step 找回所属 turn。"""

        return self._find_turn(step.turn_id)

    @staticmethod
    def _derive_objective(messages: list[dict]) -> str:
        """尽量从当前消息窗口推导任务目标。"""

        for message in reversed(messages):
            if message.get("role") != "user":
                continue
            content = message.get("content")
            if isinstance(content, str) and content.strip():
                return content.strip()[:120]
        return "bananabot task"

    @staticmethod
    def _with_step_payload(step: Step, payload: dict[str, Any] | None) -> dict[str, Any]:
        """在事件载荷里补齐 step 基本信息。"""

        merged = {
            "step_kind": step.kind,
            "step_sequence": step.sequence,
        }
        if payload:
            merged.update(payload)
        return merged

    @staticmethod
    def _merge_metadata(target: dict[str, Any], patch: dict[str, Any] | None) -> None:
        """把增量 metadata 合并进目标字典。"""

        if patch:
            target.update(patch)

    def _touch_task(self) -> None:
        """刷新 task 与 thread 的更新时间。"""

        now = _utc_now()
        self.task_run.updated_at = now
        self.thread.updated_at = now

    @staticmethod
    def _touch_turn(turn: Turn) -> None:
        """刷新 turn 更新时间。"""

        turn.updated_at = _utc_now()

    @staticmethod
    def _touch_step(step: Step) -> None:
        """刷新 step 更新时间。"""

        step.updated_at = _utc_now()

    def _persist_root_state(self) -> None:
        """持久化 thread 和 task run。"""

        if self.state_store is None:
            return
        try:
            self.state_store.save_thread(self.thread)
            self.state_store.save_task_run(self.task_run)
        except Exception:
            return

    def _persist_turn(self, turn: Turn) -> None:
        """持久化 turn。"""

        if self.state_store is None:
            return
        try:
            self.state_store.save_turn(turn)
        except Exception:
            return

    def _persist_step(self, step: Step) -> None:
        """持久化 step。"""

        if self.state_store is None:
            return
        try:
            self.state_store.save_step(step)
        except Exception:
            return

    def _persist_event(self, event: EventEnvelope) -> None:
        """持久化事件日志。"""

        if self.state_store is None:
            return
        try:
            self.state_store.append_event(event)
        except Exception:
            return
