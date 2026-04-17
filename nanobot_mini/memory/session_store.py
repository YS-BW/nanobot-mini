"""会话状态存储与持久化。

这个模块的核心目标是把“会话状态”和“文件格式”收敛在一起：
 - `Session` 表示单个会话
 - `SessionManager` 负责缓存和创建会话

在当前结构里，`Session` 负责 I/O，不负责对话编排；
对话编排由 `AppService` 和 `AgentRunner` 负责。
"""

import json
import shutil
from pathlib import Path


class Session:
    """单个持久化会话。"""

    def __init__(self, key: str, messages: list | None = None, session_dir: Path | None = None):
        """初始化会话并绑定对应文件路径。"""
        self.key = key
        self.messages = messages or []
        self._session_dir = session_dir
        self._session_path = session_dir / "session.jsonl" if session_dir else None
        self._history_path = session_dir / "history.jsonl" if session_dir else None
        self._summary_path = session_dir / "summary.jsonl" if session_dir else None

    @property
    def session_path(self) -> Path | None:
        return self._session_path

    @property
    def history_path(self) -> Path | None:
        return self._history_path

    @property
    def summary_path(self) -> Path | None:
        return self._summary_path

    @property
    def memory_path(self) -> Path | None:
        if not self._session_dir:
            return None
        return self._session_dir / "MEMORY.md"

    def add(self, role: str, content: str) -> dict:
        """向当前会话窗口追加一条消息，并立即保存。"""
        message = {"role": role, "content": content}
        self.messages.append(message)
        self.save()
        return message

    def add_batch(self, messages: list[dict]) -> None:
        """批量追加消息，并统一保存。"""
        for message in messages:
            self.messages.append({"role": message["role"], "content": message["content"]})
        self.save()

    def clear(self) -> None:
        """清空当前会话窗口。"""
        self.messages.clear()
        self.save()

    def save(self) -> None:
        """把当前会话窗口覆盖写回 `session.jsonl`。"""
        if not self._session_path:
            return
        self._session_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._session_path, "w", encoding="utf-8") as handle:
            for message in self.messages:
                handle.write(
                    json.dumps(
                        {"role": message["role"], "content": message["content"]},
                        ensure_ascii=False,
                    )
                    + "\n"
                )

    def reload(self) -> None:
        """从 `session.jsonl` 重新加载当前会话窗口。"""
        if not self._session_path or not self._session_path.exists():
            return
        with open(self._session_path, "r", encoding="utf-8") as handle:
            self.messages = [json.loads(line) for line in handle if line.strip()]

    def append_history(self, messages: list[dict]) -> None:
        """把消息持续追加到 `history.jsonl`。"""
        if not self._history_path:
            return
        self._history_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._history_path, "a", encoding="utf-8") as handle:
            for message in messages:
                handle.write(
                    json.dumps(
                        {"role": message["role"], "content": message["content"]},
                        ensure_ascii=False,
                    )
                    + "\n"
                )

    def append_summary(self, summary: str) -> None:
        """把 compact 生成的摘要追加到 `summary.jsonl`。"""
        if not self._summary_path:
            return
        self._summary_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._summary_path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps({"role": "system", "content": summary}, ensure_ascii=False) + "\n")

    def get_summary_content(self) -> list[dict]:
        """读取 `summary.jsonl` 的完整结构化内容。"""
        if not self._summary_path or not self._summary_path.exists():
            return []
        try:
            with open(self._summary_path, "r", encoding="utf-8") as handle:
                return [json.loads(line) for line in handle if line.strip()]
        except Exception:
            return []

    def get_summary_text(self) -> str:
        """把所有 summary 合并成纯文本。"""
        return "\n\n".join(entry.get("content", "") for entry in self.get_summary_content())

    def get_summary_count(self) -> int:
        """返回当前 summary 条数。"""
        return len(self.get_summary_content())

    def clear_summary(self) -> None:
        """清空 `summary.jsonl`。"""
        if self._summary_path and self._summary_path.exists():
            self._summary_path.unlink()

    def has_memory(self) -> bool:
        """判断当前会话是否已经生成长期记忆。"""
        path = self.memory_path
        return path is not None and path.exists()

    def estimate_tokens(self, messages: list[dict] | None = None) -> int:
        """用简化估算方式统计 token 数。"""
        source = messages or self.messages
        text = "\n".join(json.dumps(message, ensure_ascii=False) for message in source)
        return len(text) // 4

    @classmethod
    def load(cls, session_dir: Path) -> "Session":
        """从目录加载单个会话。"""
        session_file = session_dir / "session.jsonl"
        messages: list[dict] = []
        if session_file.exists():
            with open(session_file, "r", encoding="utf-8") as handle:
                messages = [json.loads(line) for line in handle if line.strip()]
        return cls(key=session_dir.name, messages=messages, session_dir=session_dir)


class SessionManager:
    """会话创建器与缓存管理器。"""

    def __init__(self, sessions_dir: Path):
        """初始化会话目录和内存缓存。"""
        self.sessions_dir = sessions_dir
        self.sessions_dir.mkdir(parents=True, exist_ok=True)
        self._cache: dict[str, Session] = {}

    def _get_session_dir(self, key: str) -> Path:
        """根据会话 key 计算目录路径。"""
        return self.sessions_dir / key

    def get_or_create(self, key: str) -> Session:
        """获取已有会话，不存在则从磁盘加载或创建。"""
        if key not in self._cache:
            self._cache[key] = Session.load(self._get_session_dir(key))
        return self._cache[key]

    def invalidate(self, key: str) -> None:
        """丢弃缓存，强制下次重新加载。"""
        self._cache.pop(key, None)

    def list_sessions(self) -> list[str]:
        """列出所有会话目录。"""
        return sorted(path.name for path in self.sessions_dir.iterdir() if path.is_dir())

    def delete(self, key: str) -> None:
        """删除指定会话及其目录。"""
        self._cache.pop(key, None)
        session_dir = self._get_session_dir(key)
        if session_dir.exists():
            shutil.rmtree(session_dir)
