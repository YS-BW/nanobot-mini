"""会话管理系统"""

import json
import uuid
from pathlib import Path
from datetime import datetime


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

    @property
    def session_path(self) -> Path | None:
        return self._session_path

    @property
    def history_path(self) -> Path | None:
        return self._history_path

    @property
    def summary_path(self) -> Path | None:
        return self._summary_path

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
        """保存当前会话到 session.jsonl"""
        if self._session_path:
            self._session_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self._session_path, "w", encoding="utf-8") as f:
                for msg in self.messages:
                    f.write(json.dumps(msg, ensure_ascii=False) + "\n")

    def reload(self):
        """从 session.jsonl 重新加载会话，清空内存中的消息"""
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
                record = {
                    "id": str(uuid.uuid4()),
                    "timestamp": datetime.now().isoformat(),
                    "role": msg.get("role", ""),
                    "content": msg.get("content", ""),
                }
                f.write(json.dumps(record, ensure_ascii=False) + "\n")

    def append_summary(self, summary: str):
        """追加摘要到 summary.jsonl（append-only）"""
        if not self._summary_path:
            return
        self._summary_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._summary_path, "a", encoding="utf-8") as f:
            record = {
                "id": str(uuid.uuid4()),
                "timestamp": datetime.now().isoformat(),
                "summary": summary,
                "version": 1,
            }
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    def trim_messages(self, keep_count: int):
        """裁剪消息，保留最近 N 条"""
        if keep_count >= len(self.messages):
            return
        self.messages = self.messages[-keep_count:]

    def estimate_tokens(self, messages: list[dict] | None = None) -> int:
        """估算消息列表的 token 数量"""
        msgs = messages or self.messages
        # 粗略估算：字符数 / 4
        text = "\n".join(json.dumps(m, ensure_ascii=False) for m in msgs)
        return len(text) // 4

    def compact(self, context_window: int, threshold: float = 0.70) -> tuple[list[dict], str]:
        """
        执行第一轮 compact：
        1. 检查 token 是否超过阈值
        2. 保留最近 20 条消息
        3. 返回被裁剪的消息

        Returns:
            (裁剪下来的消息列表, 空字符串占位)
        """
        # token 估算：system prompt 大约 3000 tokens，保留余量
        system_tokens = 3000
        available = context_window * threshold - system_tokens
        if self.estimate_tokens() <= available:
            return [], ""

        # 保留最近 20 条消息
        trimmed = self.messages[:-20]
        self.messages = self.messages[-20:]

        # 立即保存 trim 后的状态到 session.jsonl
        # 避免后续 chat_once 的 save() 用未 trim 的数据覆盖
        self.save()

        return trimmed, ""

    def get_summary_size(self) -> int:
        """获取 summary.jsonl 的条目数量"""
        if not self._summary_path or not self._summary_path.exists():
            return 0
        try:
            with open(self._summary_path, "r", encoding="utf-8") as f:
                return sum(1 for _ in f)
        except Exception:
            return 0

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
        """获取所有 summary 条目的纯文本内容，用于 token 估算"""
        entries = self.get_summary_content()
        return "\n\n".join(e.get("summary", "") for e in entries)

    def estimate_summary_tokens(self) -> int:
        """估算 summary.jsonl 的 token 数量（粗略：字符数 / 4）"""
        text = self.get_summary_text()
        return len(text) // 4

    def clear_summary(self):
        """清空 summary.jsonl"""
        if self._summary_path and self._summary_path.exists():
            self._summary_path.unlink()

    def get_memory_path(self) -> Path | None:
        """获取 MEMORY.md 路径（放在 session 同目录下）"""
        if not self._session_dir:
            return None
        return self._session_dir / "MEMORY.md"

    async def compact_round2(self, llm) -> str | None:
        """
        第二轮 compact：将 summary.jsonl 整合为 MEMORY.md

        Args:
            llm: LLM 实例

        Returns:
            生成的 MEMORY.md 内容，或 None 如果无需整合
        """
        summary_entries = self.get_summary_content()
        if not summary_entries:
            return None

        # 读取现有 MEMORY.md
        memory_path = self.get_memory_path()
        existing_memory = ""
        if memory_path and memory_path.exists():
            existing_memory = memory_path.read_text(encoding="utf-8")

        # 构建摘要文本
        summaries_text = "\n\n".join(
            f"## {e.get('timestamp', 'unknown')}\n{e.get('summary', '')}"
            for e in summary_entries
        )

        # 构建 prompt
        compact_prompt = f"""你是一个记忆整合助手。请将以下会话摘要整合为一份结构化的项目记忆。

{"现有记忆：" + existing_memory if existing_memory else "（暂无现有记忆）"}

---
会话摘要：
{summaries_text}

请整合成新的记忆文件，要求：
1. 合并重复信息
2. 更新过时的信息
3. 保持简洁，不超过 200 行
4. 结构化分类（项目设置、模块状态、重要决策、已知问题等）
5. 用 Markdown 格式返回
"""

        try:
            response = await llm.chat(
                messages=[{"role": "user", "content": compact_prompt}],
                tools=None,
            )
            new_memory = response.content or ""
            if new_memory and new_memory.strip():
                # 写入 MEMORY.md
                if memory_path:
                    memory_path.parent.mkdir(parents=True, exist_ok=True)
                    memory_path.write_text(new_memory.strip(), encoding="utf-8")
                # 清空 summary.jsonl
                self.clear_summary()
                return new_memory.strip()
        except Exception:
            pass
        return None

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
