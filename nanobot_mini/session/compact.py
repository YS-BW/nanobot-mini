"""Compact 服务层"""

from .store import Session


class CompactService:
    """会话压缩服务"""

    KEEP_COUNT = 20  # 固定保留消息条数

    def __init__(self, session: Session, llm, config):
        self.session = session
        self.llm = llm
        self.config = config

    async def run_if_needed(self, force: bool = False) -> bool:
        """检查并执行 compact，返回是否执行了 compact"""
        if not force and not self._should_compact():
            return False
        await self._compact()
        return True

    def _should_compact(self) -> bool:
        """检查是否需要 compact"""
        threshold_tokens = int(self.config.context_window * self.config.compact_threshold_round1)
        return self.session.estimate_tokens() > threshold_tokens

    async def _compact(self):
        """执行第一轮 compact"""
        trimmed = self._get_trimmed()
        if not trimmed:
            return

        # 保存被裁切的消息到 history
        if trimmed:
            self.session.append_history(trimmed)

        # 生成 summary
        summary = await self._generate_summary(trimmed)
        if summary:
            self.session.append_summary(summary.strip())

        # 检查是否需要第二轮 compact
        if self.session.get_summary_count() >= 25:
            await self._compact_round2()

    def _get_trimmed(self) -> list[dict]:
        """获取要裁切的消息"""
        if len(self.session.messages) > self.KEEP_COUNT:
            trimmed = self.session.messages[:-self.KEEP_COUNT]
            self.session.messages = self.session.messages[-self.KEEP_COUNT:]
        else:
            # 消息少于 KEEP_COUNT，全部作为 trimmed
            trimmed = self.session.messages.copy()
            self.session.messages = []

        self.session.save()
        return trimmed

    async def _generate_summary(self, trimmed: list[dict]) -> str:
        """调用 LLM 生成 summary"""
        dialog_content = []
        for m in trimmed:
            role = m.get("role", "")
            content = m.get("content", "")[:500]
            if role == "tool":
                dialog_content.append(f"[tool] {content}")
            else:
                dialog_content.append(f"[{role}] {content}")

        prompt = f"""你是一个会话总结助手。请从以下对话中提取关键信息，生成一条主题总结。

对话内容：
{chr(10).join(dialog_content)}

要求：
- 一句话描述用户的需求和模型的回答
- 如果有调用工具，包含关键 tool 结果
- 简洁，不超过 100 字
- 格式：用户需求 + 模型回答（含关键结果）

示例：用户询问项目结构，模型查看了nanobot_mini目录，列出了__main__.py、session.py等核心文件"""

        for attempt in range(5):
            try:
                response = await self.llm.chat(
                    messages=[{"role": "user", "content": prompt}],
                    tools=None,
                )
                if response.content and response.content.strip():
                    return response.content
            except Exception:
                if attempt == 4:
                    break
        return ""

    async def _compact_round2(self):
        """第二轮 compact：将 summary 整合为 MEMORY.md"""
        summary_entries = self.session.get_summary_content()
        if not summary_entries:
            return

        # 读取现有 memory
        memory_path = self.session.memory_path
        existing_memory = ""
        if memory_path and memory_path.exists():
            existing_memory = memory_path.read_text(encoding="utf-8")

        # 构建摘要文本
        summaries_text = "\n\n".join(f"- {e.get('content', '')}" for e in summary_entries)
        memory_header = f"## 现有记忆\n{existing_memory}" if existing_memory else "（暂无现有记忆）"

        prompt = f"""你是一个记忆整合助手。请将以下会话摘要整合为一份结构化的项目记忆。

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
            response = await self.llm.chat(
                messages=[{"role": "user", "content": prompt}],
                tools=None,
            )
            new_memory = response.content or ""
            if new_memory and new_memory.strip() and memory_path:
                memory_path.parent.mkdir(parents=True, exist_ok=True)
                memory_path.write_text(new_memory.strip(), encoding="utf-8")
                self.session.clear_summary()
        except Exception:
            pass
