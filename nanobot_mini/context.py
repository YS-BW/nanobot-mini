"""消息上下文构建器"""

import json
import platform
from datetime import datetime
from pathlib import Path

from .memory import MemoryStore


def _get_platform_policy() -> str:
    """获取平台策略"""
    system = platform.system()
    if system == "Windows":
        return """## 平台策略 (Windows)
- 当前运行在 Windows 系统上。
- 部分 GNU 工具（如 grep、sed、awk）可能不可用。
- 优先使用 Windows 原生命令或文件工具。"""
    else:
        return """## 平台策略 (POSIX)
- 当前运行在 POSIX 兼容系统上。
- 优先使用 UTF-8 编码和标准 Shell 工具。
- 当文件工具更简单可靠时，优先使用文件工具而非 shell 命令。"""


# 系统提示词模板
SYSTEM_PROMPT_TEMPLATE = """# 🍌 BananaBot

你是 BananaBot，杠精+梗王。默认别人说的不对，第一反应是反驳。

## 表达
- 强口语化 + 梗（典中典/绷不住了/给我整不会了/离谱）
- 短句，反问句多，节奏快
- 轻口脏话：卧槽/我靠/我真服了/离谱

## 示例
"卧槽，你这就绷不住了？前提都没了你在这推结果？典中典。"
"不是，你先把概念搞明白行不行？越说越离谱。"
"我靠，你这是自证循环搁这套娃呢？还能被你说成分析，笑死。"

## 工具
exec: 执行 Shell 命令，参数 command / timeout

## 运行信息
- 系统: {system} {machine}
- Python: {python_version}
- 当前时间: {time}
- 工作目录: {workspace}

{platform_policy}
"""


def _load_summary(session) -> str:
    """加载 session 的 summary.jsonl 内容

    格式：{"role": "system", "content": "..."}
    """
    if not session.summary_path or not session.summary_path.exists():
        return ""
    try:
        summaries = []
        with open(session.summary_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    data = json.loads(line)
                    summaries.append(data.get("content", ""))
        if summaries:
            return "\n\n".join(f"## 会话摘要\n{s}" for s in summaries if s)
        return ""
    except Exception:
        return ""


class ContextBuilder:
    """构建发送给 LLM 的消息列表"""

    def __init__(self, workspace: Path, global_dir: Path, memory_store: MemoryStore | None = None):
        self.workspace = workspace
        self.global_dir = global_dir
        self.memory_store = memory_store or MemoryStore(workspace, global_dir)

    def build_messages(self, session=None) -> list[dict]:
        """
        构建消息列表

        Args:
            session: Session 实例（用于加载 session.messages、memory、summary）

        Returns:
            完整的消息列表
        """
        parts = []

        # 1. 全局 BANANA.md
        global_banana = self.global_dir / "BANANA.md"
        if global_banana.exists():
            content = global_banana.read_text(encoding="utf-8")
            parts.append(f"# 全局指令\n\n{content}")

        # 2. 项目 BANANA.md（从 workspace 向上查找）
        project_banana = MemoryStore.find_banana_md(self.workspace)
        if project_banana:
            content = project_banana.read_text(encoding="utf-8")
            parts.append(f"# 项目指令\n\n{content}")

        # 构建消息列表
        # 顺序：memory/summary → system prompt → session.messages
        messages = []

        # 1. Memory 或 Summary 作为独立的 system 消息（互斥）
        if session:
            memory_path = session.get_memory_path()
            if memory_path and memory_path.exists():
                content = memory_path.read_text(encoding="utf-8")
                if content.strip():
                    messages.append({"role": "system", "content": content})
            else:
                summary_context = _load_summary(session)
                if summary_context:
                    messages.append({"role": "system", "content": summary_context})

        # 2. 系统提示词
        system_prompt = SYSTEM_PROMPT_TEMPLATE.format(
            system=platform.system(),
            machine=platform.machine(),
            python_version=platform.python_version(),
            time=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            workspace=self.workspace,
            platform_policy=_get_platform_policy(),
        )
        messages.append({"role": "system", "content": system_prompt})

        # 3. 拼接 session.messages（包含当前输入）
        if session:
            messages.extend(session.messages)

        return messages
