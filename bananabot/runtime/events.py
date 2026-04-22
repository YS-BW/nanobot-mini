"""运行时事件模型。"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import uuid4


def _event_id() -> str:
    """生成稳定事件 ID。"""

    return f"evt_{uuid4().hex}"


@dataclass(slots=True)
class EventEnvelope:
    """统一运行时事件 envelope。"""

    type: str
    status: str = "running"
    message: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)
    thread_id: str | None = None
    task_run_id: str | None = None
    turn_id: str | None = None
    step_id: str | None = None
    event_id: str = field(default_factory=_event_id)
    timestamp: datetime = field(default_factory=datetime.utcnow)
