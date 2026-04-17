"""compact 与记忆阈值策略。

策略层的目的是把“什么时候 compact、保留多少、什么时候滚动成长期记忆”
这类规则从具体执行逻辑里拆出来。
"""

from dataclasses import dataclass


@dataclass
class CompactPolicy:
    """compact 决策策略。"""

    context_window: int
    round1_threshold: float
    round2_threshold: float
    keep_count: int = 20
    summary_rollup_count: int = 25

    def should_compact(self, token_count: int) -> bool:
        """根据当前 token 数判断是否需要第一轮 compact。"""
        return token_count > int(self.context_window * self.round1_threshold)

    def should_rollup_summary(self, summary_count: int) -> bool:
        """根据 summary 数量判断是否要整合为长期记忆。"""
        return summary_count >= self.summary_rollup_count
