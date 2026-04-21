"""项目级长期记忆辅助对象。

这个对象和 `Session` 的职责不同：
 - `Session` 管当前会话窗口与会话文件
 - `MemoryStore` 管项目级长期记忆与指令文件查找
"""

import hashlib
from pathlib import Path


class MemoryStore:
    """按项目隔离的长期记忆存储。"""

    def __init__(self, workspace: Path, global_dir: Path):
        self.workspace = workspace
        self.global_dir = global_dir
        project_hash = hashlib.md5(str(workspace.resolve()).encode()).hexdigest()[:8]
        self.memory_dir = global_dir / "projects" / project_hash / "memory"
        self.memory_dir.mkdir(parents=True, exist_ok=True)

    def get_memory_context(self) -> str | None:
        memory_file = self.memory_dir / "MEMORY.md"
        if not memory_file.exists():
            return None
        return "\n".join(memory_file.read_text(encoding="utf-8").splitlines()[:200])

    def save_memory(self, content: str) -> None:
        (self.memory_dir / "MEMORY.md").write_text(content, encoding="utf-8")

    def add_note(self, topic: str, content: str) -> None:
        safe_topic = "".join(char if char.isalnum() or char in "-_" else "_" for char in topic)
        (self.memory_dir / f"{safe_topic}.md").write_text(content, encoding="utf-8")

    def list_notes(self) -> list[str]:
        return [path.stem for path in self.memory_dir.glob("*.md") if path.stem != "MEMORY"]

    @staticmethod
    def find_banana_md(workspace: Path) -> Path | None:
        """从当前工作目录向上查找项目指令文件。"""
        current = workspace.resolve()
        for parent in [current] + list(current.parents):
            banana = parent / "BANANA.md"
            if banana.exists():
                return banana
            hidden = parent / ".bananabot" / "BANANA.md"
            if hidden.exists():
                return hidden
        return None
