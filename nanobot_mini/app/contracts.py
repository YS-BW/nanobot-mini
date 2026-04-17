"""应用层统一请求、响应和事件结构。"""

from dataclasses import dataclass
from typing import Any


@dataclass
class ChatRequest:
    """统一聊天请求。"""

    session_id: str
    user_input: str
    metadata: dict[str, Any] | None = None


@dataclass
class ChatResponse:
    """统一聊天响应。"""

    session_id: str
    message: str
    finish_reason: str = "stop"


@dataclass
class AgentEvent:
    """统一事件结构，供 CLI、Web、桌面端消费。"""

    type: str
    session_id: str
    message: str | None = None
    data: dict[str, Any] | None = None
