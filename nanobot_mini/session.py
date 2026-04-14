"""极简 Session 管理"""
import json
from pathlib import Path
from datetime import datetime


class Session:
    def __init__(self, key: str, messages: list = None, path: Path = None):
        self.key = key
        self.messages = messages or []
        self._path = path

    def add(self, role: str, content: str, **kwargs):
        msg = {"role": role, "content": content, "timestamp": datetime.now().isoformat()}
        msg.update(kwargs)
        self.messages.append(msg)
        return msg

    def history(self) -> list:
        return self.messages.copy()

    def save(self):
        if self._path:
            self._path.write_text(json.dumps(self.messages, ensure_ascii=False))


class SessionManager:
    def __init__(self, workspace: str):
        self.workspace = Path(workspace)
        self.sessions_dir = self.workspace / "sessions"
        self.sessions_dir.mkdir(parents=True, exist_ok=True)
        self._cache: dict = {}

    def get_or_create(self, key: str) -> Session:
        if key not in self._cache:
            path = self.sessions_dir / f"{key}.jsonl"
            if path.exists():
                messages = json.loads(path.read_text())
            else:
                messages = []
            self._cache[key] = Session(key=key, messages=messages, path=path)
        return self._cache[key]

    def save(self, session: Session):
        session.save()
