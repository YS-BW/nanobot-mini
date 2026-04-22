"""运行时状态持久化骨架。

这个模块只提供 Phase 1 过渡期需要的最小文件存储能力：

1. 把 `Thread / TaskRun / Turn / Step` 以 JSON 形式分别落盘；
2. 把统一 `EventEnvelope` 以 JSONL 方式追加到事件日志；
3. 提供一个测试友好的 `RuntimeSnapshot` 读取视图，便于后续运行时回归测试。

它故意保持简单，不提前引入数据库、锁或复杂索引。
后续 runtime-core 真正接入时，可以直接复用目录结构或整体替换实现。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, fields
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

from bananabot.runtime.events import EventEnvelope
from bananabot.runtime.models import (
    Step,
    StepKind,
    StepStatus,
    TaskRun,
    TaskRunStatus,
    ThreadRef,
    Turn,
    TurnStatus,
)


@dataclass(slots=True)
class RuntimeSnapshot:
    """聚合某个 thread 的最小状态快照。"""

    thread: ThreadRef | None
    task_runs: list[TaskRun]
    turns: list[Turn]
    steps: list[Step]
    events: list[EventEnvelope]


class FileRuntimeStateStore:
    """基于本地文件的最小运行时状态仓库。"""

    def __init__(self, root: Path):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def save_thread(self, thread: ThreadRef) -> None:
        """持久化一个 thread。"""

        self._write_json(self._entity_path("threads", thread.id), self._serialize_dataclass(thread))

    def save_task_run(self, task_run: TaskRun) -> None:
        """持久化一个 task run。"""

        self._write_json(self._entity_path("task_runs", task_run.id), self._serialize_dataclass(task_run))

    def save_turn(self, turn: Turn) -> None:
        """持久化一个 turn。"""

        self._write_json(self._entity_path("turns", turn.id), self._serialize_dataclass(turn))

    def save_step(self, step: Step) -> None:
        """持久化一个 step。"""

        self._write_json(self._entity_path("steps", step.id), self._serialize_dataclass(step))

    def append_event(self, event: EventEnvelope) -> None:
        """把统一事件追加写入 JSONL 事件日志。"""

        path = self.root / "event_log.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(self._serialize_dataclass(event), ensure_ascii=False) + "\n")

    def load_thread(self, thread_id: str) -> ThreadRef | None:
        """读取一个 thread。"""

        return self._load_entity("threads", thread_id, self._deserialize_thread)

    def load_task_run(self, task_run_id: str) -> TaskRun | None:
        """读取一个 task run。"""

        return self._load_entity("task_runs", task_run_id, self._deserialize_task_run)

    def load_turn(self, turn_id: str) -> Turn | None:
        """读取一个 turn。"""

        return self._load_entity("turns", turn_id, self._deserialize_turn)

    def load_step(self, step_id: str) -> Step | None:
        """读取一个 step。"""

        return self._load_entity("steps", step_id, self._deserialize_step)

    def list_task_runs(self, thread_id: str) -> list[TaskRun]:
        """列出某个 thread 下的 task run。"""

        items = [
            task_run
            for task_run in self._load_entities("task_runs", self._deserialize_task_run)
            if task_run.thread_id == thread_id
        ]
        return sorted(items, key=lambda item: (item.created_at, item.id))

    def list_turns(self, task_run_id: str) -> list[Turn]:
        """列出某个 task run 下的 turn。"""

        items = [
            turn
            for turn in self._load_entities("turns", self._deserialize_turn)
            if turn.task_run_id == task_run_id
        ]
        return sorted(items, key=lambda item: (item.sequence, item.created_at, item.id))

    def list_steps(self, turn_id: str) -> list[Step]:
        """列出某个 turn 下的 step。"""

        items = [
            step
            for step in self._load_entities("steps", self._deserialize_step)
            if step.turn_id == turn_id
        ]
        return sorted(items, key=lambda item: (item.sequence, item.created_at, item.id))

    def load_events(
        self,
        *,
        thread_id: str | None = None,
        task_run_id: str | None = None,
        turn_id: str | None = None,
        step_id: str | None = None,
    ) -> list[EventEnvelope]:
        """按运行时身份过滤读取事件日志。"""

        path = self.root / "event_log.jsonl"
        if not path.exists():
            return []

        items: list[EventEnvelope] = []
        with open(path, "r", encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                event = self._deserialize_event(json.loads(line))
                if thread_id is not None and event.thread_id != thread_id:
                    continue
                if task_run_id is not None and event.task_run_id != task_run_id:
                    continue
                if turn_id is not None and event.turn_id != turn_id:
                    continue
                if step_id is not None and event.step_id != step_id:
                    continue
                items.append(event)

        return sorted(items, key=lambda item: (item.timestamp, item.event_id))

    def load_runtime_snapshot(self, thread_id: str) -> RuntimeSnapshot:
        """读取某个 thread 的最小聚合快照。"""

        thread = self.load_thread(thread_id)
        task_runs = self.list_task_runs(thread_id)
        turns: list[Turn] = []
        steps: list[Step] = []

        for task_run in task_runs:
            task_turns = self.list_turns(task_run.id)
            turns.extend(task_turns)
            for turn in task_turns:
                steps.extend(self.list_steps(turn.id))

        events = self.load_events(thread_id=thread_id)
        return RuntimeSnapshot(thread=thread, task_runs=task_runs, turns=turns, steps=steps, events=events)

    def _entity_path(self, directory: str, entity_id: str) -> Path:
        """计算实体文件路径。"""

        return self.root / directory / f"{entity_id}.json"

    def _write_json(self, path: Path, data: dict[str, Any]) -> None:
        """以 UTF-8 JSON 覆盖写入文件。"""

        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)

    def _load_entity(self, directory: str, entity_id: str, loader) -> Any | None:
        """按 ID 读取单个实体。"""

        path = self._entity_path(directory, entity_id)
        if not path.exists():
            return None
        with open(path, "r", encoding="utf-8") as handle:
            return loader(json.load(handle))

    def _load_entities(self, directory: str, loader) -> list[Any]:
        """读取目录中的所有实体。"""

        base = self.root / directory
        if not base.exists():
            return []

        items: list[Any] = []
        for path in sorted(base.glob("*.json")):
            with open(path, "r", encoding="utf-8") as handle:
                items.append(loader(json.load(handle)))
        return items

    @staticmethod
    def _serialize_dataclass(value: Any) -> dict[str, Any]:
        """把 dataclass 对象转换成可持久化字典。"""

        return {field.name: FileRuntimeStateStore._serialize_value(getattr(value, field.name)) for field in fields(value)}

    @staticmethod
    def _serialize_value(value: Any) -> Any:
        """递归处理 datetime / enum / 容器。"""

        if isinstance(value, datetime):
            return value.isoformat()
        if isinstance(value, Enum):
            return value.value
        if isinstance(value, dict):
            return {key: FileRuntimeStateStore._serialize_value(item) for key, item in value.items()}
        if isinstance(value, list):
            return [FileRuntimeStateStore._serialize_value(item) for item in value]
        return value

    @staticmethod
    def _parse_datetime(value: str | None) -> datetime:
        """把 ISO 时间恢复成 datetime。"""

        if not value:
            return datetime.utcnow()
        return datetime.fromisoformat(value)

    @classmethod
    def _deserialize_thread(cls, data: dict[str, Any]) -> ThreadRef:
        """恢复 ThreadRef。"""

        return ThreadRef(
            id=data["id"],
            title=data.get("title"),
            metadata=dict(data.get("metadata") or {}),
            created_at=cls._parse_datetime(data.get("created_at")),
            updated_at=cls._parse_datetime(data.get("updated_at")),
        )

    @classmethod
    def _deserialize_task_run(cls, data: dict[str, Any]) -> TaskRun:
        """恢复 TaskRun。"""

        return TaskRun(
            thread_id=data["thread_id"],
            objective=data["objective"],
            id=data["id"],
            status=TaskRunStatus(data["status"]),
            metadata=dict(data.get("metadata") or {}),
            created_at=cls._parse_datetime(data.get("created_at")),
            updated_at=cls._parse_datetime(data.get("updated_at")),
        )

    @classmethod
    def _deserialize_turn(cls, data: dict[str, Any]) -> Turn:
        """恢复 Turn。"""

        return Turn(
            task_run_id=data["task_run_id"],
            sequence=data["sequence"],
            id=data["id"],
            status=TurnStatus(data["status"]),
            created_at=cls._parse_datetime(data.get("created_at")),
            updated_at=cls._parse_datetime(data.get("updated_at")),
        )

    @classmethod
    def _deserialize_step(cls, data: dict[str, Any]) -> Step:
        """恢复 Step。"""

        return Step(
            task_run_id=data["task_run_id"],
            turn_id=data["turn_id"],
            kind=StepKind(data["kind"]),
            sequence=data["sequence"],
            id=data["id"],
            status=StepStatus(data["status"]),
            payload=dict(data.get("payload") or {}),
            created_at=cls._parse_datetime(data.get("created_at")),
            updated_at=cls._parse_datetime(data.get("updated_at")),
        )

    @classmethod
    def _deserialize_event(cls, data: dict[str, Any]) -> EventEnvelope:
        """恢复 EventEnvelope。"""

        payload = dict(data.get("payload") or {})
        return EventEnvelope(
            type=data["type"],
            status=data.get("status", "running"),
            message=data.get("message"),
            payload=payload,
            thread_id=data.get("thread_id"),
            task_run_id=data.get("task_run_id"),
            turn_id=data.get("turn_id"),
            step_id=data.get("step_id"),
            event_id=data.get("event_id"),
            timestamp=cls._parse_datetime(data.get("timestamp")),
        )
