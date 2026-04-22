"""context engine 可消费的记忆来源定义。

这个模块的职责很单一：
- 把 memory 层里的不同来源收敛成统一 `ContextSource`
- 明确每种来源的优先级和注入文本格式
- 不直接参与运行时消息拼装

后续 runtime/context_engine 只需要消费这里产出的 source，
而不用自己知道 thread summary、project memory、working memory 各自怎么读。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .memory_store import MemoryStore
from .thread_store import ThreadStore
from .working_memory import WorkingMemory


@dataclass(slots=True)
class ContextSource:
    """单个可注入上下文来源。"""

    name: str
    role: str
    content: str
    priority: int = 100
    metadata: dict[str, Any] = field(default_factory=dict)

    def as_message(self) -> dict[str, str]:
        """转成模型消息结构。"""

        return {"role": self.role, "content": self.content}


def collect_memory_context_sources(
    *,
    thread_store: ThreadStore | None = None,
    memory_store: MemoryStore | None = None,
    working_memory: WorkingMemory | None = None,
) -> list[ContextSource]:
    """收集 memory 层提供给 context engine 的上下文来源。

    这里先固定优先级：
    1. working memory
    2. 项目级长期记忆
    3. thread 级长期记忆
    4. thread 级 compact summary（仅在没有 thread 长期记忆时回退）
    """

    sources: list[ContextSource] = []

    working_source = build_working_memory_source(working_memory)
    if working_source:
        sources.append(working_source)

    project_source = build_project_memory_source(memory_store)
    if project_source:
        sources.append(project_source)

    thread_memory_source = build_thread_memory_source(thread_store)
    if thread_memory_source:
        sources.append(thread_memory_source)
    else:
        thread_summary_source = build_thread_summary_source(thread_store)
        if thread_summary_source:
            sources.append(thread_summary_source)

    return sorted(sources, key=lambda item: item.priority)


def build_working_memory_source(memory: WorkingMemory | None) -> ContextSource | None:
    """把 working memory 转成高优先级 source。"""

    if memory is None:
        return None

    content = memory.to_prompt_block().strip()
    if not content:
        return None

    return ContextSource(
        name="working_memory",
        role="system",
        content=content,
        priority=10,
        metadata={
            "thread_id": memory.thread_id,
            "task_run_id": memory.task_run_id,
        },
    )


def build_project_memory_source(memory_store: MemoryStore | None) -> ContextSource | None:
    """读取项目级长期记忆。"""

    if memory_store is None:
        return None

    content = _compact_text(memory_store.get_memory_context())
    if not content:
        return None

    return ContextSource(
        name="project_memory",
        role="system",
        content=content,
        priority=20,
        metadata={"scope": "project"},
    )


def build_thread_memory_source(thread_store: ThreadStore | None) -> ContextSource | None:
    """读取 thread 目录里的长期记忆文件。"""

    if thread_store is None or not thread_store.has_memory() or not thread_store.memory_path:
        return None

    content = _read_text(thread_store.memory_path)
    if not content:
        return None

    return ContextSource(
        name="thread_memory",
        role="system",
        content=content,
        priority=30,
        metadata={"thread_id": thread_store.key},
    )


def build_thread_summary_source(thread_store: ThreadStore | None) -> ContextSource | None:
    """在没有长期记忆时回退到 compact summary。"""

    if thread_store is None:
        return None

    content = _compact_text(thread_store.get_summary_text())
    if not content:
        return None

    return ContextSource(
        name="thread_summary",
        role="system",
        content=content,
        priority=40,
        metadata={"thread_id": thread_store.key},
    )


def _read_text(path: Path) -> str | None:
    """安全读取文本文件。"""

    try:
        return _compact_text(path.read_text(encoding="utf-8"))
    except OSError:
        return None


def _compact_text(content: str | None) -> str | None:
    """去掉两端空白，空内容返回 `None`。"""

    if content is None:
        return None
    text = content.strip()
    if not text:
        return None
    return text
