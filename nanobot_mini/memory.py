"""记忆管理系统"""

import hashlib
from pathlib import Path


class MemoryStore:
    """记忆存储管理器，按项目隔离"""

    def __init__(self, workspace: Path, global_dir: Path):
        self.workspace = workspace
        self.global_dir = global_dir
        # 项目记忆目录（按 cwd hash 隔离）
        project_hash = hashlib.md5(str(workspace.resolve()).encode()).hexdigest()[:8]
        self.memory_dir = global_dir / "projects" / project_hash / "memory"
        self.memory_dir.mkdir(parents=True, exist_ok=True)

    def get_memory_context(self) -> str | None:
        """
        获取记忆上下文（MEMORY.md 前 200 行）

        Returns:
            记忆内容字符串，或 None 如果没有记忆
        """
        memory_file = self.memory_dir / "MEMORY.md"
        if not memory_file.exists():
            return None
        lines = memory_file.read_text(encoding="utf-8").splitlines()[:200]
        return "\n".join(lines)

    def save_memory(self, content: str):
        """保存记忆到 MEMORY.md"""
        memory_file = self.memory_dir / "MEMORY.md"
        memory_file.write_text(content, encoding="utf-8")

    def add_note(self, topic: str, content: str):
        """添加主题记忆到单独文件"""
        # 清理 topic 名称
        safe_topic = "".join(c if c.isalnum() or c in "-_" else "_" for c in topic)
        topic_file = self.memory_dir / f"{safe_topic}.md"
        topic_file.write_text(content, encoding="utf-8")

    def list_notes(self) -> list[str]:
        """列出所有主题记忆文件"""
        return [p.stem for p in self.memory_dir.glob("*.md") if p.stem != "MEMORY"]

    @staticmethod
    def find_banana_md(workspace: Path) -> Path | None:
        """
        从 workspace 向上查找 BANANA.md

        Returns:
            找到的 BANANA.md 路径，或 None
        """
        current = workspace.resolve()
        # 从当前目录向上查找
        for parent in [current] + list(current.parents):
            # 检查当前目录
            banana = parent / "BANANA.md"
            if banana.exists():
                return banana
            # 检查 .bananabot 目录
            hidden = parent / ".bananabot" / "BANANA.md"
            if hidden.exists():
                return hidden
        return None
