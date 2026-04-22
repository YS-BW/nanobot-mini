"""应用层统一请求、响应和事件结构。"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(slots=True)
class TaskRequest:
    """面向 runtime 的任务请求。"""

    thread_id: str
    objective: str
    task_run_id: str | None = None
    metadata: dict[str, Any] | None = None


@dataclass(slots=True)
class TaskResponse:
    """面向 task runtime 的统一响应。"""

    thread_id: str
    task_run_id: str
    output: str
    finish_reason: str = "stop"
    status: str = "completed"
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class AgentEvent:
    """统一事件结构，供 CLI、Web、桌面端消费。"""

    type: str
    thread_id: str
    task_run_id: str | None = None
    turn_id: str | None = None
    step_id: str | None = None
    status: str = "running"
    message: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)
    event_id: str | None = None
    timestamp: datetime | None = None

    def __post_init__(self) -> None:
        """补齐默认时间。"""

        if self.timestamp is None:
            self.timestamp = datetime.utcnow()
