"""会话存储层"""

import json
from pathlib import Path


class Session:
    """单次会话，管理对话历史"""

    def __init__(self, key: str, messages: list | None = None, session_dir: Path | None = None):
        self.key = key
        self.messages = messages or []
        self._session_dir = session_dir
        # 文件路径
        self._session_path = session_dir / "session.jsonl" if session_dir else None
        self._history_path = session_dir / "history.jsonl" if session_dir else None
        self._summary_path = session_dir / "summary.jsonl" if session_dir else None

    # ========== 属性 ==========

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
        """获取 MEMORY.md 路径"""
        if not self._session_dir:
            return None
        return self._session_dir / "MEMORY.md"

    # ========== 消息操作 ==========

    def add(self, role: str, content: str):
        """添加消息到会话（自动持久化）"""
        msg = {"role": role, "content": content}
        self.messages.append(msg)
        self._save()
        return msg

    def add_batch(self, messages: list[dict]):
        """批量添加消息（自动持久化）"""
        for msg in messages:
            self.messages.append({"role": msg["role"], "content": msg["content"]})
        self._save()

    def clear(self):
        """清空会话历史"""
        self.messages.clear()
        self._save()

    # ========== 文件 I/O ==========

    def _save(self):
        """保存当前会话到 session.jsonl"""
        if self._session_path:
            self._session_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self._session_path, "w", encoding="utf-8") as f:
                for msg in self.messages:
                    f.write(json.dumps({"role": msg["role"], "content": msg["content"]}, ensure_ascii=False) + "\n")

    def save(self):
        """保存当前会话到 session.jsonl"""
        self._save()

    def reload(self):
        """从 session.jsonl 重新加载会话"""
        if self._session_path and self._session_path.exists():
            with open(self._session_path, "r", encoding="utf-8") as f:
                self.messages = []
                for line in f:
                    line = line.strip()
                    if line:
                        self.messages.append(json.loads(line))

    def append_history(self, messages: list[dict]):
        """追加消息到 history.jsonl（append-only）"""
        if not self._history_path:
            return
        self._history_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._history_path, "a", encoding="utf-8") as f:
            for msg in messages:
                f.write(json.dumps({"role": msg["role"], "content": msg["content"]}, ensure_ascii=False) + "\n")

    def append_summary(self, summary: str):
        """追加摘要到 summary.jsonl（格式：{"role": "system", "content": "..."}）"""
        if not self._summary_path:
            return
        self._summary_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._summary_path, "a", encoding="utf-8") as f:
            f.write(json.dumps({"role": "system", "content": summary}, ensure_ascii=False) + "\n")

    # ========== Summary 操作 ==========

    def get_summary_content(self) -> list[dict]:
        """获取 summary.jsonl 的所有条目"""
        if not self._summary_path or not self._summary_path.exists():
            return []
        try:
            entries = []
            with open(self._summary_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        entries.append(json.loads(line))
            return entries
        except Exception:
            return []

    def get_summary_text(self) -> str:
        """获取所有 summary 的纯文本内容"""
        entries = self.get_summary_content()
        return "\n\n".join(e.get("content", "") for e in entries)

    def get_summary_count(self) -> int:
        """获取 summary.jsonl 的条目数量"""
        return len(self.get_summary_content())

    def clear_summary(self):
        """清空 summary.jsonl"""
        if self._summary_path and self._summary_path.exists():
            self._summary_path.unlink()

    # ========== Memory 操作 ==========

    def has_memory(self) -> bool:
        """检查 memory.md 是否存在"""
        path = self.memory_path
        return path is not None and path.exists()

    # ========== Token 估算 ==========

    def estimate_tokens(self, messages: list[dict] | None = None) -> int:
        """估算消息列表的 token 数量"""
        msgs = messages or self.messages
        text = "\n".join(json.dumps(m, ensure_ascii=False) for m in msgs)
        return len(text) // 4

    # ========== 类方法 ==========

    @classmethod
    def load(cls, session_dir: Path) -> "Session":
        """从目录加载会话"""
        session_file = session_dir / "session.jsonl"
        messages = []
        if session_file.exists():
            with open(session_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        messages.append(json.loads(line))
        return cls(key=session_dir.name, messages=messages, session_dir=session_dir)


class SessionManager:
    """会话管理器，负责会话的创建、缓存和持久化"""

    def __init__(self, sessions_dir: Path):
        self.sessions_dir = sessions_dir
        self.sessions_dir.mkdir(parents=True, exist_ok=True)
        self._cache: dict[str, Session] = {}

    def _get_session_dir(self, key: str) -> Path:
        """获取 session 目录路径"""
        return self.sessions_dir / key

    def get_or_create(self, key: str) -> Session:
        """获取或创建会话"""
        if key in self._cache:
            return self._cache[key]

        session_dir = self._get_session_dir(key)
        session = Session.load(session_dir)
        self._cache[key] = session
        return session

    def invalidate(self, key: str):
        """清除缓存，强制下次 get_or_create 从文件重新加载"""
        self._cache.pop(key, None)

    def list_sessions(self) -> list[str]:
        """列出所有会话"""
        return [p.name for p in self.sessions_dir.iterdir() if p.is_dir()]

    def delete(self, key: str):
        """删除会话"""
        if key in self._cache:
            del self._cache[key]
        import shutil
        session_dir = self._get_session_dir(key)
        if session_dir.exists():
            shutil.rmtree(session_dir)
