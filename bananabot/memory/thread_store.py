"""线程消息存储与持久化。

这个模块是当前消息存储层的主命名入口：
 - `ThreadStore` 表示单个 thread 的消息目录
 - `ThreadStoreManager` 负责缓存和创建 thread store

当前落盘格式仍沿用历史文件名：
 - `session.jsonl`：当前短期消息窗口
 - `history.jsonl`：完整历史日志
 - `summary.jsonl`：compact 摘要
 - `MEMORY.md`：thread 级长期记忆

也就是说，名字已经切到 thread 语义，但磁盘格式暂时不改，避免阶段 1
把命名重构和存储迁移耦在一起。
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path


class ThreadStore:
    """单个 thread 的持久化消息存储。"""

    def __init__(self, key: str, messages: list | None = None, thread_dir: Path | None = None):
        """初始化存储对象并绑定对应目录。"""

        self.key = key
        self.messages = messages or []
        self._thread_dir = thread_dir
        self._session_path = thread_dir / "session.jsonl" if thread_dir else None
        self._history_path = thread_dir / "history.jsonl" if thread_dir else None
        self._summary_path = thread_dir / "summary.jsonl" if thread_dir else None

    @property
    def thread_id(self) -> str:
        """返回当前 thread 标识。"""

        return self.key

    @property
    def thread_path(self) -> Path | None:
        """返回当前 thread 目录。"""

        return self._thread_dir

    @property
    def session_path(self) -> Path | None:
        """返回当前窗口消息文件路径。"""

        return self._session_path

    @property
    def history_path(self) -> Path | None:
        return self._history_path

    @property
    def summary_path(self) -> Path | None:
        return self._summary_path

    @property
    def memory_path(self) -> Path | None:
        if not self._thread_dir:
            return None
        return self._thread_dir / "MEMORY.md"

    def add_message(self, message: dict) -> dict:
        """向当前短期消息窗口追加一条消息，并立即保存。"""

        self.messages.append(dict(message))
        self.save()
        return message

    def add(self, role: str, content: str) -> dict:
        """追加一条基础 role/content 消息。"""

        return self.add_message({"role": role, "content": content})

    def add_batch(self, messages: list[dict]) -> None:
        """批量追加消息，并统一落盘。"""

        for message in messages:
            self.messages.append(dict(message))
        self.save()

    def clear(self) -> None:
        """清空当前短期消息窗口。"""

        self.messages.clear()
        self.save()

    def save(self) -> None:
        """把当前窗口覆盖写回 `session.jsonl`。"""

        if not self._session_path:
            return
        self._session_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._session_path, "w", encoding="utf-8") as handle:
            for message in self.messages:
                handle.write(json.dumps(message, ensure_ascii=False) + "\n")

    def reload(self) -> None:
        """从 `session.jsonl` 重新加载当前窗口。"""

        if not self._session_path or not self._session_path.exists():
            return
        with open(self._session_path, "r", encoding="utf-8") as handle:
            self.messages = [json.loads(line) for line in handle if line.strip()]

    def append_history(self, messages: list[dict]) -> None:
        """持续追加完整历史消息到 `history.jsonl`。"""

        if not self._history_path:
            return
        self._history_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._history_path, "a", encoding="utf-8") as handle:
            for message in messages:
                handle.write(json.dumps(message, ensure_ascii=False) + "\n")

    def append_summary(self, summary: str) -> None:
        """把 compact 摘要追加到 `summary.jsonl`。"""

        if not self._summary_path:
            return
        self._summary_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._summary_path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps({"role": "system", "content": summary}, ensure_ascii=False) + "\n")

    def get_summary_content(self) -> list[dict]:
        """读取全部摘要结构。"""

        if not self._summary_path or not self._summary_path.exists():
            return []
        try:
            with open(self._summary_path, "r", encoding="utf-8") as handle:
                return [json.loads(line) for line in handle if line.strip()]
        except Exception:
            return []

    def get_summary_text(self) -> str:
        """把摘要合并成纯文本。"""

        return "\n\n".join(entry.get("content", "") for entry in self.get_summary_content())

    def get_summary_count(self) -> int:
        """返回当前摘要条数。"""

        return len(self.get_summary_content())

    def clear_summary(self) -> None:
        """清空 `summary.jsonl`。"""

        if self._summary_path and self._summary_path.exists():
            self._summary_path.unlink()

    def has_memory(self) -> bool:
        """判断当前 thread 是否已经生成长期记忆。"""

        path = self.memory_path
        return path is not None and path.exists()

    def estimate_tokens(self, messages: list[dict] | None = None) -> int:
        """用粗略规则估算 token 数。"""

        source = messages or self.messages
        text = "\n".join(json.dumps(message, ensure_ascii=False) for message in source)
        return len(text) // 4

    @classmethod
    def load(cls, thread_dir: Path) -> "ThreadStore":
        """从目录加载单个 thread store。"""

        session_file = thread_dir / "session.jsonl"
        messages: list[dict] = []
        if session_file.exists():
            with open(session_file, "r", encoding="utf-8") as handle:
                messages = [json.loads(line) for line in handle if line.strip()]
        return cls(key=thread_dir.name, messages=messages, thread_dir=thread_dir)


class ThreadStoreManager:
    """thread store 的创建器与缓存管理器。"""

    def __init__(self, threads_dir: Path):
        """初始化 thread 根目录和内存缓存。"""

        self.threads_dir = threads_dir
        self.sessions_dir = threads_dir
        self.threads_dir.mkdir(parents=True, exist_ok=True)
        self._cache: dict[str, ThreadStore] = {}

    def _get_thread_dir(self, thread_id: str) -> Path:
        """根据 thread_id 计算目录路径。"""

        return self.threads_dir / thread_id

    def get_thread_dir(self, thread_id: str) -> Path:
        """返回指定 thread 的目录路径。"""

        return self._get_thread_dir(thread_id)

    def get_or_create_thread(self, thread_id: str) -> ThreadStore:
        """获取已有 thread store，不存在则从磁盘加载或创建。"""

        if thread_id not in self._cache:
            self._cache[thread_id] = ThreadStore.load(self._get_thread_dir(thread_id))
        return self._cache[thread_id]

    def invalidate(self, key: str) -> None:
        """丢弃缓存，强制下次重新加载。"""

        self._cache.pop(key, None)

    def list_threads(self) -> list[str]:
        """列出所有 thread 目录。"""

        return sorted(path.name for path in self.threads_dir.iterdir() if path.is_dir())

    def delete_thread(self, thread_id: str) -> None:
        """删除指定 thread 目录。"""

        self._cache.pop(thread_id, None)
        thread_dir = self._get_thread_dir(thread_id)
        if thread_dir.exists():
            shutil.rmtree(thread_dir)


__all__ = [
    "ThreadStore",
    "ThreadStoreManager",
]
