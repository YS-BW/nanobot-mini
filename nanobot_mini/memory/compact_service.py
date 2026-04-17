"""会话压缩与长期记忆整合服务。

这个模块只负责 compact 相关流程，不直接参与正常对话执行。

当前 compact 分两层：
 - 第一层：裁剪 `session.messages`，生成 `summary.jsonl`
 - 第二层：把累计 summary 整合成 `MEMORY.md`

第一阶段只完成了结构收敛，没有升级 compact 能力模型本身。
"""

from .policy import CompactPolicy
from .session_store import Session


class CompactService:
    """执行 compact 与记忆整合。"""

    def __init__(self, session: Session, llm, config):
        self.session = session
        self.llm = llm
        self.config = config
        self.policy = CompactPolicy(
            context_window=config.context_window,
            round1_threshold=config.compact_threshold_round1,
            round2_threshold=config.compact_threshold_round2,
        )

    async def run_if_needed(self, force: bool = False) -> bool:
        """按策略决定是否执行 compact。"""
        if not force and not self.policy.should_compact(self.session.estimate_tokens()):
            return False
        await self._compact()
        return True

    async def _compact(self) -> None:
        """执行一轮 compact。"""
        trimmed = self._get_trimmed()
        if not trimmed:
            return

        # 当前定义下，history 是完整日志，因此 compact 不再重复写 history。
        summary = await self._generate_summary(trimmed)
        if summary:
            self.session.append_summary(summary.strip())

        if self.policy.should_rollup_summary(self.session.get_summary_count()):
            await self._compact_round2()

    def _get_trimmed(self) -> list[dict]:
        """取出本轮要从 session 中裁掉的消息。"""
        if len(self.session.messages) > self.policy.keep_count:
            trimmed = self.session.messages[:-self.policy.keep_count]
            self.session.messages = self.session.messages[-self.policy.keep_count :]
        else:
            trimmed = self.session.messages.copy()
            self.session.messages = []
        self.session.save()
        return trimmed

    async def _generate_summary(self, trimmed: list[dict]) -> str:
        """调用模型，把被裁剪消息压缩成一条主题摘要。"""
        dialog_content = []
        for message in trimmed:
            role = message.get("role", "")
            content = message.get("content", "")[:500]
            prefix = "[tool]" if role == "tool" else f"[{role}]"
            dialog_content.append(f"{prefix} {content}")

        prompt = f"""你是一个会话总结助手。请从以下对话中提取关键信息，生成一条主题总结。

对话内容：
{chr(10).join(dialog_content)}

要求：
- 一句话描述用户的需求和模型的回答
- 如果有调用工具，包含关键 tool 结果
- 简洁，不超过 100 字
- 格式：用户需求 + 模型回答（含关键结果）
"""

        for attempt in range(5):
            try:
                response = await self.llm.chat(messages=[{"role": "user", "content": prompt}], tools=None)
                if response.content and response.content.strip():
                    return response.content
            except Exception:
                if attempt == 4:
                    break
        return ""

    async def _compact_round2(self) -> None:
        """把累计摘要整合成长期记忆。"""
        summary_entries = self.session.get_summary_content()
        if not summary_entries:
            return

        memory_path = self.session.memory_path
        existing_memory = ""
        if memory_path and memory_path.exists():
            existing_memory = memory_path.read_text(encoding="utf-8")

        summaries_text = "\n\n".join(f"- {entry.get('content', '')}" for entry in summary_entries)
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
            response = await self.llm.chat(messages=[{"role": "user", "content": prompt}], tools=None)
            content = response.content or ""
            if content.strip() and memory_path:
                memory_path.parent.mkdir(parents=True, exist_ok=True)
                memory_path.write_text(content.strip(), encoding="utf-8")
                self.session.clear_summary()
        except Exception:
            pass
