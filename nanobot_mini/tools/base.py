"""工具基类定义。"""

from abc import ABC, abstractmethod


class Tool(ABC):
    """所有工具的统一基类。"""

    @property
    @abstractmethod
    def name(self) -> str:
        """工具名称"""
        ...

    @property
    @abstractmethod
    def description(self) -> str:
        """工具描述，用于 LLM 理解工具用途"""
        ...

    @property
    def parameters(self) -> dict:
        """OpenAI function calling 格式的参数定义"""
        return {"type": "object", "properties": {}}

    @abstractmethod
    async def execute(self, **kwargs) -> str:
        """执行工具逻辑，返回执行结果字符串"""
        ...
