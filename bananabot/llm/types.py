"""LLM 层的数据结构。

这里区分两类返回：

1. `LLMResponse`
   用于一次性非流式结果，适合 compact、测试和最终归档。
2. `LLMStreamChunk`
   用于流式增量结果，既能承载普通文本增量，也能承载工具调用的增量片段。

第二类是这次加流式支持的关键。很多 OpenAI 兼容模型在 stream 模式下，
工具调用不会一次性给全，而是会把 `id / name / arguments` 拆成多段往外吐。
因此这里专门建模，避免上层拿字符串硬拼，最后搞得一团糟。
"""

from dataclasses import dataclass, field


@dataclass
class ToolCall:
    """模型生成的工具调用。"""

    id: str
    name: str
    arguments: dict


@dataclass
class LLMResponse:
    """结构化聊天响应。"""

    content: str | None
    tool_calls: list[ToolCall] = field(default_factory=list)
    finish_reason: str = "stop"
    reasoning_content: str | None = None
    assistant_message: dict | None = None


@dataclass
class ToolCallDelta:
    """流式工具调用增量。

    `index` 用来标识这是第几个 tool call。
    同一个调用的 `id`、`name`、`arguments_chunk` 可能分多次到达，
    上层需要按 index 聚合后才能还原成最终的 `ToolCall`。
    """

    index: int
    id: str | None = None
    name: str | None = None
    arguments_chunk: str = ""


@dataclass
class LLMStreamChunk:
    """流式聊天片段。

    一个 chunk 可能只包含文本，也可能只包含工具调用增量，
    也可能只包含思考过程，或者三者都没有，仅仅携带 `finish_reason`。
    """

    reasoning_content: str = ""
    content: str = ""
    tool_calls: list[ToolCallDelta] = field(default_factory=list)
    finish_reason: str | None = None
