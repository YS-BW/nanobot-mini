"""运行时领域模型。

这些对象是下一轮 runtime 重构的共享契约。
当前阶段先把对象模型冻结下来，便于并发改造 `runtime / memory / tools / app`
时使用同一套语义，不再围绕“单轮 chat loop”继续堆逻辑。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4


def _new_id(prefix: str) -> str:
    """生成带前缀的稳定字符串 ID。"""

    return f"{prefix}_{uuid4().hex}"


def _utc_now() -> datetime:
    """统一生成当前 UTC 时间。"""

    return datetime.utcnow()


class TaskRunStatus(StrEnum):
    """任务运行状态。"""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class TurnStatus(StrEnum):
    """单轮执行状态。"""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class StepStatus(StrEnum):
    """原子步骤状态。"""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class StepKind(StrEnum):
    """运行时步骤类型。"""

    REASONING = "reasoning"
    TOOL_CALL_REQUESTED = "tool_call_requested"
    TOOL_CALL_STARTED = "tool_call_started"
    TOOL_CALL_FINISHED = "tool_call_finished"
    ASSISTANT_MESSAGE = "assistant_message"


@dataclass(slots=True)
class ThreadRef:
    """表示一个持续存在的 thread。"""

    id: str
    title: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=_utc_now)
    updated_at: datetime = field(default_factory=_utc_now)


@dataclass(slots=True)
class TaskRun:
    """表示 thread 下的一次任务运行。"""

    thread_id: str
    objective: str
    id: str = field(default_factory=lambda: _new_id("task"))
    status: TaskRunStatus = TaskRunStatus.PENDING
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=_utc_now)
    updated_at: datetime = field(default_factory=_utc_now)


@dataclass(slots=True)
class Turn:
    """表示 task run 内的一轮 agent 决策。"""

    task_run_id: str
    sequence: int
    id: str = field(default_factory=lambda: _new_id("turn"))
    status: TurnStatus = TurnStatus.PENDING
    created_at: datetime = field(default_factory=_utc_now)
    updated_at: datetime = field(default_factory=_utc_now)


@dataclass(slots=True)
class Step:
    """表示 turn 内的一次原子执行动作。"""

    task_run_id: str
    turn_id: str
    kind: StepKind
    sequence: int
    id: str = field(default_factory=lambda: _new_id("step"))
    status: StepStatus = StepStatus.PENDING
    payload: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=_utc_now)
    updated_at: datetime = field(default_factory=_utc_now)
