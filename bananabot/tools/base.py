"""工具基类定义。"""

from abc import ABC, abstractmethod

from .specs import ToolSpec


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

    @property
    def spec(self) -> ToolSpec:
        """返回工具的标准化描述。"""
        return ToolSpec(
            name=self.name,
            description=self.description,
            parameters=self.parameters,
        )

    def definition(self) -> dict:
        """返回给模型消费的 function calling 定义。"""
        return self.spec.to_definition()

    @abstractmethod
    async def execute(self, **kwargs) -> str:
        """执行工具逻辑，返回执行结果字符串"""
        ...
