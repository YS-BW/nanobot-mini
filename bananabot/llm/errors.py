"""LLM 相关异常。"""


class LLMError(Exception):
    """LLM 层基础异常。"""


class LLMResponseError(LLMError):
    """当模型返回结构异常时抛出。"""
