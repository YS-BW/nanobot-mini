"""消息上下文构建器"""

import json
import platform
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from .memory import MemoryStore

if TYPE_CHECKING:
    from .session import Session


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

你是 BananaBot，一个混迹贴吧多年的老哥，典型"杠精+梗王"。

## 核心人设

- 默认别人说的不对，第一反应是反驳
- 不只是骂，而是"边喷边讲逻辑"
- 喜欢抓漏洞、抬杠、扣细节
- 情绪容易上来，会夹杂口头脏话（卧槽/我靠/我真服了/离谱）
- 有一点优越感，觉得别人很多时候没想明白

## 表达风格

- 强口语化 + 网络梗 + 短句
- 开头直接打断或否定（不要铺垫）
- 多用反问句压制对方
- 节奏要快，像连发评论
- 嘲讽、阴阳怪气要自然，不要刻意

## 脏话规则

- 仅限轻度口头表达：卧槽 / 我靠 / 我真服了 / 离谱
- 用来加强情绪，而不是纯骂人
- 不连续堆砌，不低级

## 常用梗（必须多用）

- "典中典""绷不住了""笑死""离谱"
- "你这波属于是…""建议直接…"
- "给我整不会了""属实是…"
- "搁这套娃呢？""自证循环是吧？"
- "节目效果拉满了"

## 攻击方式

- 开局否定 + 情绪词（卧槽/我靠）
- 抓一个逻辑点狠狠干
- 用梗+反问持续压制
- 假装夸，其实在损

## 输出要求

- 每次 2~4 句话
- 至少包含：
  - 1个否定/质疑
  - 1句反问
  - 1~2个梗
- 可以自然带1个轻脏话
- 不解释背景，不总结

## 示例

1. "卧槽，你这就绷不住了？前提都没了你在这推结果？典中典属于是。"

2. "我靠，你这是自证循环搁这套娃呢？还能被你说成分析，笑死。"

3. "不是，你先把概念搞明白行不行？越说越离谱，给我整不会了。"

4. "说你呢，别划走，你这就是不懂还要硬讲，节目效果拉满。"

## 工具使用

### exec — 执行 Shell 命令
- 功能: 执行 Shell 命令并返回输出
- 参数: command (命令), timeout (超时秒数，默认 60)
- 只有当用户明确要求执行命令、或需要获取信息时才使用
- 日常对话直接回复，不需要调用工具

## 运行信息
- 系统: {system} {machine}
- Python: {python_version}
- 当前时间: {time}
- 工作目录: {workspace}

{platform_policy}
"""


def _load_summary(session) -> str:
    """加载 session 的 summary.jsonl 内容"""
    if not session.summary_path or not session.summary_path.exists():
        return ""
    try:
        summaries = []
        with open(session.summary_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    data = json.loads(line)
                    summaries.append(data.get("summary", ""))
        if summaries:
            return "\n\n".join(f"## 会话摘要\n{ s}" for s in summaries if s)
        return ""
    except Exception:
        return ""


class ContextBuilder:
    """构建发送给 LLM 的消息列表"""

    def __init__(self, workspace: Path, global_dir: Path, memory_store: MemoryStore | None = None):
        self.workspace = workspace
        self.global_dir = global_dir
        self.memory_store = memory_store or MemoryStore(workspace, global_dir)

    def build_messages(
        self,
        history: list[dict],
        current_message: str,
        session=None,
    ) -> list[dict]:
        """
        构建消息列表

        Args:
            history: 历史消息列表
            current_message: 当前用户输入
            session: Session 实例（可选，用于加载 summary.jsonl）

        Returns:
            完整的消息列表，包含系统消息、历史消息和当前消息
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

        # 3. 记忆（session 目录下的 MEMORY.md）
        if session:
            memory_path = session.get_memory_path()
            if memory_path and memory_path.exists():
                content = memory_path.read_text(encoding="utf-8")
                if content.strip():
                    parts.append(f"# 记忆\n\n{content}")

        # 4. 会话摘要（summary.jsonl）
        if session:
            summary_context = _load_summary(session)
            if summary_context:
                parts.append(f"# 会话摘要\n\n{summary_context}")

        # 5. 系统提示词
        parts.append(SYSTEM_PROMPT_TEMPLATE.format(
            system=platform.system(),
            machine=platform.machine(),
            python_version=platform.python_version(),
            time=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            workspace=self.workspace,
            platform_policy=_get_platform_policy(),
        ))

        system_content = "\n\n---\n\n".join(parts)

        messages = [{"role": "system", "content": system_content}]
        messages.extend(history)
        messages.append({"role": "user", "content": current_message})

        return messages
