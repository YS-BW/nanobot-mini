"""运行时上下文组装。"""

from __future__ import annotations

from pathlib import Path

from ..memory.context_sources import collect_memory_context_sources
from ..memory.memory_store import MemoryStore
from ..memory.thread_store import ThreadStore
from ..memory.working_memory import WorkingMemory, WorkingMemoryStore
from .models import TaskRun, ThreadRef
from .prompts import build_system_prompt


def build_context(
    *,
    workspace: Path,
    thread_store: ThreadStore | None = None,
    thread: ThreadRef | None = None,
    task_run: TaskRun | None = None,
    messages: list[dict] | None = None,
    memory_store: MemoryStore | None = None,
    working_memory: WorkingMemory | None = None,
    working_memory_store: WorkingMemoryStore | None = None,
    system_prompt: str | None = None,
    extra_system_messages: list[str] | None = None,
) -> list[dict]:
    """按当前 thread 和记忆来源直接组装模型上下文。"""

    active_working_memory = working_memory or _load_working_memory(
        thread_store=thread_store,
        thread=thread,
        task_run=task_run,
        working_memory_store=working_memory_store,
    )
    sources = collect_memory_context_sources(
        thread_store=thread_store,
        memory_store=memory_store,
        working_memory=active_working_memory,
    )
    result: list[dict] = [source.as_message() for source in sources]

    prompt_text = (system_prompt or build_system_prompt(workspace)).strip()
    if prompt_text:
        result.append({"role": "system", "content": prompt_text})

    for extra_message in extra_system_messages or []:
        content = extra_message.strip()
        if content:
            result.append({"role": "system", "content": content})

    result.extend(sanitize_messages(_resolve_messages(thread_store=thread_store, messages=messages)))
    return result


def sanitize_messages(messages: list[dict]) -> list[dict]:
    """清理历史消息里的无效结构。"""

    sanitized: list[dict] = []
    for raw_message in messages:
        message = dict(raw_message)
        role = message.get("role")

        if role == "assistant":
            if not message.get("tool_calls") and not message.get("content"):
                continue
            sanitized.append(message)
            continue

        if role == "tool":
            if not sanitized:
                continue
            previous = sanitized[-1]
            if previous.get("role") != "assistant" or not previous.get("tool_calls"):
                continue
            if not message.get("tool_call_id"):
                tool_calls = previous.get("tool_calls") or []
                if len(tool_calls) == 1 and isinstance(tool_calls[0], dict):
                    message["tool_call_id"] = tool_calls[0].get("id")
            if not message.get("tool_call_id"):
                continue
            sanitized.append(message)
            continue

        sanitized.append(message)

    return sanitized


def _load_working_memory(
    *,
    thread_store: ThreadStore | None,
    thread: ThreadRef | None,
    task_run: TaskRun | None,
    working_memory_store: WorkingMemoryStore | None,
) -> WorkingMemory | None:
    """按 thread/task 标识恢复 working memory。"""

    if working_memory_store is None:
        return None

    thread_id = _resolve_thread_id(thread_store=thread_store, thread=thread)
    if thread_id is None:
        return None

    task_run_id = task_run.id if task_run else None
    memory = working_memory_store.load(thread_id=thread_id, task_run_id=task_run_id)
    if memory is not None:
        return memory
    if task_run_id:
        return working_memory_store.load(thread_id=thread_id)
    return None


def _resolve_messages(*, thread_store: ThreadStore | None, messages: list[dict] | None) -> list[dict]:
    """确定当前轮要拼进去的消息窗口。"""

    if messages is not None:
        return list(messages)
    if thread_store is not None:
        return list(thread_store.messages)
    return []


def _resolve_thread_id(*, thread_store: ThreadStore | None, thread: ThreadRef | None) -> str | None:
    """解析当前上下文对应的 thread 标识。"""

    if thread is not None:
        return thread.id
    if thread_store is not None:
        return thread_store.key
    return None
