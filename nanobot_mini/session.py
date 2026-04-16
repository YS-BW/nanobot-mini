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
        """添加消息到会话（只保存 role + content）"""
        msg = {
            "role": role,
            "content": content,
        }
        self.messages.append(msg)
        return msg

    def history(self) -> list:
        """获取消息历史副本"""
        return self.messages.copy()

    def clear(self):
        """清空会话历史"""
        self.messages.clear()

    def save(self):
        """保存当前会话到 session.jsonl（只写 role + content）"""
        if self._session_path:
            self._session_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self._session_path, "w", encoding="utf-8") as f:
                for msg in self.messages:
                    # 只写 role 和 content（与 messages 结构一致）
                    f.write(json.dumps({"role": msg["role"], "content": msg["content"]}, ensure_ascii=False) + "\n")

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
        """追加消息到 history.jsonl（append-only，只写 role + content）"""
        if not self._history_path:
            return
        self._history_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._history_path, "a", encoding="utf-8") as f:
            for msg in messages:
                # 只写 role 和 content（与 session.jsonl/messages 结构一致）
                f.write(json.dumps({"role": msg["role"], "content": msg["content"]}, ensure_ascii=False) + "\n")

    def append_summary(self, summary: str):
        """追加摘要到 summary.jsonl（append-only）

        格式：{"role": "system", "content": "用户需求 + 模型回答 + tool结果"}
        """
        if not self._summary_path:
            return
        self._summary_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._summary_path, "a", encoding="utf-8") as f:
            record = {
                "role": "system",
                "content": summary,
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

    def _calc_keep_count(self, context_window: int, threshold: float = 0.70) -> int:
        """
        计算保留消息条数

        按设计文档：固定保留 20 条
        """
        return 20

    async def compact(
        self,
        llm,
        context_window: int,
        threshold: float = 0.70,
        max_retries: int = 5,
        force: bool = False,
    ) -> tuple[list[dict], str]:
        """
        执行第一轮 compact：
        1. 检查 token 是否超过阈值（force=True 时跳过）
        2. 保留最近消息（根据窗口计算）
        3. 裁剪消息写入 history.jsonl
        4. 调用 LLM 生成 1 条 summary（当前主题：用户需求 + 模型回答 + tool 结果）
        5. 失败重试（最多 max_retries 次）

        Returns:
            (裁剪下来的消息列表, summary 内容)
        """
        if not force:
            system_tokens = 3000
            available = context_window * threshold - system_tokens
            if self.estimate_tokens() <= available:
                return [], ""

        keep_count = self._calc_keep_count(context_window, threshold)

        # 获取要 compact 的消息（保留最近 keep_count 条，其余裁切）
        if len(self.messages) > keep_count:
            trimmed = self.messages[:-keep_count]
            self.messages = self.messages[-keep_count:]
        else:
            # 消息少于 keep_count，全部作为 trimmed
            trimmed = self.messages.copy()
            self.messages = []  # 清空 session（用 summary 代替）

        self.save()

        # 追加到 history.jsonl
        if trimmed:
            self.append_history(trimmed)

        # 构建对话内容用于生成 summary
        dialog_content = []
        for m in trimmed:
            role = m.get("role", "")
            content = m.get("content", "")[:500]
            if role == "tool":
                dialog_content.append(f"[tool] {content}")
            else:
                dialog_content.append(f"[{role}] {content}")

        summary_prompt = f"""你是一个会话总结助手。请从以下对话中提取关键信息，生成一条主题总结。

对话内容：
{chr(10).join(dialog_content)}

要求：
- 一句话描述用户的需求和模型的回答
- 如果有调用工具，包含关键 tool 结果
- 简洁，不超过 100 字
- 格式：用户需求 + 模型回答（含关键结果）

示例：用户询问项目结构，模型查看了nanobot_mini目录，列出了__main__.py、session.py等核心文件"""

        for attempt in range(max_retries):
            try:
                response = await llm.chat(
                    messages=[{"role": "user", "content": summary_prompt}],
                    tools=None,
                )
                summary = response.content or ""
                if summary.strip():
                    self.append_summary(summary.strip())
                    return trimmed, summary
            except Exception:
                if attempt == max_retries - 1:
                    # 最后一次失败，原生消息已写入 history，不丢数据
                    break

        return trimmed, ""

    def get_summary_content(self) -> list[dict]:
        """获取 summary.jsonl 的所有条目

        格式：{"role": "system", "content": "..."}
        """
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
        return "\n\n".join(e.get("content", "") for e in entries)

    def get_summary_count(self) -> int:
        """获取 summary.jsonl 的条目数量"""
        return len(self.get_summary_content())

    def clear_summary(self):
        """清空 summary.jsonl"""
        if self._summary_path and self._summary_path.exists():
            self._summary_path.unlink()

    def get_memory_path(self) -> Path | None:
        """获取 MEMORY.md 路径（放在 session 同目录下）"""
        if not self._session_dir:
            return None
        return self._session_dir / "MEMORY.md"

    def has_memory(self) -> bool:
        """检查 memory.md 是否存在"""
        path = self.get_memory_path()
        return path is not None and path.exists()

    async def compact_round2(self, llm) -> str | None:
        """
        第二轮 compact：将 summary.jsonl 整合为 MEMORY.md

        将所有 summary 条目压缩成 1 条，写入 memory.md，然后清空 summary.jsonl

        Args:
            llm: LLM 实例

        Returns:
            生成的 MEMORY.md 内容，或 None 如果无需整合
        """
        summary_entries = self.get_summary_content()
        if not summary_entries:
            return None

        # 读取现有 MEMORY.md（如果有的话，用于合并）
        memory_path = self.get_memory_path()
        existing_memory = ""
        if memory_path and memory_path.exists():
            existing_memory = memory_path.read_text(encoding="utf-8")

        # 构建摘要文本（每条 summary 的 content 字段）
        summaries_text = "\n\n".join(
            f"- {e.get('content', '')}"
            for e in summary_entries
        )

        # 构建 prompt
        memory_header = f"## 现有记忆\n{existing_memory}" if existing_memory else "（暂无现有记忆）"
        compact_prompt = f"""你是一个记忆整合助手。请将以下会话摘要整合为一份结构化的项目记忆。

{memory_header}

---
## 新会话摘要
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
                # 清空 summary.jsonl（重新累积）
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
