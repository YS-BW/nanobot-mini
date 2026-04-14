"""会话管理系统"""

import json
from pathlib import Path
from datetime import datetime


class Session:
    """单次会话，管理对话历史"""

    def __init__(self, key: str, messages: list | None = None, path: Path | None = None):
        self.key = key
        self.messages = messages or []
        self._path = path

    def add(self, role: str, content: str, **kwargs):
        """添加消息到会话"""
        msg = {
            "role": role,
            "content": content,
            "timestamp": datetime.now().isoformat(),
        }
        msg.update(kwargs)
        self.messages.append(msg)
        return msg

    def history(self) -> list:
        """获取消息历史副本"""
        return self.messages.copy()

    def clear(self):
        """清空会话历史"""
        self.messages.clear()

    def save(self):
        """保存会话到文件（JSONL 格式）"""
        if self._path:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            with open(self._path, "w", encoding="utf-8") as f:
                for msg in self.messages:
                    f.write(json.dumps(msg, ensure_ascii=False) + "\n")

    @classmethod
    def load(cls, path: Path) -> "Session":
        """从文件加载会话（JSONL 格式）"""
        messages = []
        if path.exists():
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        messages.append(json.loads(line))
        return cls(key=path.stem, messages=messages, path=path)


class SessionManager:
    """会话管理器，负责会话的创建、缓存和持久化"""

    def __init__(self, workspace: str):
        self.workspace = Path(workspace)
        self.sessions_dir = self.workspace / "sessions"
        self._cache: dict[str, Session] = {}

    def get_or_create(self, key: str) -> Session:
        """获取或创建会话"""
        if key in self._cache:
            return self._cache[key]

        path = self.sessions_dir / f"{key}.jsonl"
        session = Session.load(path)
        self._cache[key] = session
        return session

    def list_sessions(self) -> list[str]:
        """列出所有会话"""
        self.sessions_dir.mkdir(parents=True, exist_ok=True)
        return [p.stem for p in self.sessions_dir.glob("*.jsonl")]

    def delete(self, key: str):
        """删除会话"""
        if key in self._cache:
            del self._cache[key]
        path = self.sessions_dir / f"{key}.jsonl"
        if path.exists():
            path.unlink()
