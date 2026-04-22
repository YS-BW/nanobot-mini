"""working memory 数据结构与最小存储接口。

这一层是 Phase 2 的过渡骨架，目标不是马上替换现有 session 机制，
而是先把 agent 在“单次任务执行期间需要持续记住什么”收敛成统一对象。

当前提供两部分：
1. `WorkingMemory`：结构化的短期运行记忆。
2. `WorkingMemoryStore` / `FileWorkingMemoryStore`：最小可落地的持久化接口。

设计要点：
- `thread_id` 是 working memory 的主归属对象。
- `task_run_id` 可选，用于后续把 thread 级和 task 级记忆拆开。
- 先落 JSON 文件存储，便于调试、恢复和后续迁移。
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any


def _utc_now() -> datetime:
    """统一生成当前 UTC 时间。"""

    return datetime.utcnow()


@dataclass(slots=True)
class WorkingMemory:
    """运行中任务的结构化短期记忆。

    这里刻意不直接存完整消息历史，而是只保留 runtime 和 context engine
    真正需要反复引用的关键信息，避免 working memory 退化成另一份聊天记录。
    """

    thread_id: str
    task_run_id: str | None = None
    objective: str | None = None
    user_intent: str | None = None
    summary: str | None = None
    current_plan: list[str] = field(default_factory=list)
    constraints: list[str] = field(default_factory=list)
    pending_actions: list[str] = field(default_factory=list)
    open_questions: list[str] = field(default_factory=list)
    recent_facts: list[str] = field(default_factory=list)
    tool_observations: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=_utc_now)
    updated_at: datetime = field(default_factory=_utc_now)

    def touch(self) -> None:
        """刷新更新时间。"""

        self.updated_at = _utc_now()

    def to_dict(self) -> dict[str, Any]:
        """转成可稳定落盘的字典结构。"""

        return {
            "thread_id": self.thread_id,
            "task_run_id": self.task_run_id,
            "objective": self.objective,
            "user_intent": self.user_intent,
            "summary": self.summary,
            "current_plan": list(self.current_plan),
            "constraints": list(self.constraints),
            "pending_actions": list(self.pending_actions),
            "open_questions": list(self.open_questions),
            "recent_facts": list(self.recent_facts),
            "tool_observations": list(self.tool_observations),
            "metadata": dict(self.metadata),
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "WorkingMemory":
        """从存储结构恢复 working memory。"""

        return cls(
            thread_id=data["thread_id"],
            task_run_id=data.get("task_run_id"),
            objective=data.get("objective"),
            user_intent=data.get("user_intent"),
            summary=data.get("summary"),
            current_plan=list(data.get("current_plan") or []),
            constraints=list(data.get("constraints") or []),
            pending_actions=list(data.get("pending_actions") or []),
            open_questions=list(data.get("open_questions") or []),
            recent_facts=list(data.get("recent_facts") or []),
            tool_observations=list(data.get("tool_observations") or []),
            metadata=dict(data.get("metadata") or {}),
            created_at=_parse_datetime(data.get("created_at")),
            updated_at=_parse_datetime(data.get("updated_at")),
        )

    def to_prompt_block(self, max_items: int = 8) -> str:
        """转成可直接注入 system context 的文本块。

        这里保持简洁，只输出 runtime 真正需要的结构化字段，
        让 context engine 可以稳定地把 working memory 放到消息最前面。
        """

        lines = ["## Working Memory"]

        if self.objective:
            lines.append(f"- 当前任务目标：{self.objective}")
        if self.user_intent:
            lines.append(f"- 当前用户意图：{self.user_intent}")
        if self.summary:
            lines.append(f"- 当前摘要：{self.summary}")

        _append_list_block(lines, "当前计划", self.current_plan, max_items=max_items)
        _append_list_block(lines, "约束", self.constraints, max_items=max_items)
        _append_list_block(lines, "待执行动作", self.pending_actions, max_items=max_items)
        _append_list_block(lines, "未决问题", self.open_questions, max_items=max_items)
        _append_list_block(lines, "最近事实", self.recent_facts, max_items=max_items)
        _append_list_block(lines, "工具观察", self.tool_observations, max_items=max_items)

        return "\n".join(line for line in lines if line.strip())


class WorkingMemoryStore(ABC):
    """working memory 最小存储接口。

    先只定义 `load / save / clear` 三个动作，避免现在把存储层做得过重。
    后续如果引入数据库或更细的 memory scope，也只需要替换实现类。
    """

    @abstractmethod
    def load(self, thread_id: str, task_run_id: str | None = None) -> WorkingMemory | None:
        """按 thread 或 task 读取 working memory。"""

    @abstractmethod
    def save(self, memory: WorkingMemory) -> None:
        """持久化 working memory。"""

    @abstractmethod
    def clear(self, thread_id: str, task_run_id: str | None = None) -> None:
        """清除已保存的 working memory。"""

    def load_or_create(
        self,
        thread_id: str,
        task_run_id: str | None = None,
        *,
        objective: str | None = None,
    ) -> WorkingMemory:
        """读取已有状态，不存在则创建最小空壳。"""

        existing = self.load(thread_id=thread_id, task_run_id=task_run_id)
        if existing is not None:
            return existing
        return WorkingMemory(thread_id=thread_id, task_run_id=task_run_id, objective=objective)


class FileWorkingMemoryStore(WorkingMemoryStore):
    """基于 JSON 文件的 working memory 存储。

    默认目录结构：
    - `root_dir/<thread_id>/working-memory.json`
    - `root_dir/<thread_id>/tasks/<task_run_id>/working-memory.json`

    这样既能兼容现有按会话目录落盘的方式，也能平滑过渡到未来的 thread/task 模型。
    """

    def __init__(self, root_dir: Path):
        self.root_dir = root_dir
        self.root_dir.mkdir(parents=True, exist_ok=True)

    def load(self, thread_id: str, task_run_id: str | None = None) -> WorkingMemory | None:
        """读取指定 thread 或 task 的 working memory。"""

        path = self.get_path(thread_id=thread_id, task_run_id=task_run_id)
        if not path.exists():
            return None
        payload = json.loads(path.read_text(encoding="utf-8"))
        return WorkingMemory.from_dict(payload)

    def save(self, memory: WorkingMemory) -> None:
        """把 working memory 保存到目标路径。"""

        memory.touch()
        path = self.get_path(thread_id=memory.thread_id, task_run_id=memory.task_run_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(memory.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def clear(self, thread_id: str, task_run_id: str | None = None) -> None:
        """删除指定范围的 working memory 文件。"""

        path = self.get_path(thread_id=thread_id, task_run_id=task_run_id)
        if path.exists():
            path.unlink()

    def get_path(self, thread_id: str, task_run_id: str | None = None) -> Path:
        """返回 working memory 对应的文件路径。"""

        thread_dir = self.root_dir / thread_id
        if task_run_id:
            return thread_dir / "tasks" / task_run_id / "working-memory.json"
        return thread_dir / "working-memory.json"


def _parse_datetime(raw: str | None) -> datetime:
    """容错解析存储中的时间字段。"""

    if not raw:
        return _utc_now()
    try:
        return datetime.fromisoformat(raw)
    except ValueError:
        return _utc_now()


def _append_list_block(lines: list[str], title: str, items: list[str], *, max_items: int) -> None:
    """把列表字段收敛成固定格式的文本块。"""

    clean_items = [item.strip() for item in items if item and item.strip()]
    if not clean_items:
        return

    lines.append(f"### {title}")
    for item in clean_items[:max_items]:
        lines.append(f"- {item}")
