"""运行时事件模型。

运行时事件只在内部流转，用来把 `AgentRunner` 的中间状态传给 `AppService`。
之后 `AppService` 再把它们转换成面向客户端的统一事件结构。
"""

from dataclasses import dataclass
from typing import Any


@dataclass
class RuntimeEvent:
    """运行时内部事件。"""

    type: str
    message: str | None = None
    data: dict[str, Any] | None = None
