"""应用服务依赖组装。

这个模块只负责一件事：把分散在各层的对象按当前默认配置组装起来，
得到一个可以直接给 CLI 或其他客户端使用的 `AppService`。

第一阶段重构后，所有入口都应该尽量从这里拿到默认服务，而不是在各自
入口里重复 new `LLMClient`、`ToolRegistry`、`ThreadStoreManager`。
"""

from ..infra import Config
from ..llm import LLMClient
from ..memory import ThreadStoreManager
from ..tools import ExecTool, ToolRegistry
from .service import AppService


def create_app_service(config: Config | None = None) -> AppService:
    """按配置创建默认应用服务。

    这里组装的是“当前项目的默认运行时”：
    - LLM：使用 `models.toml + .env` 中声明的模型与密钥
    - Tools：注册当前内置工具
    - Thread stores：使用全局 thread 目录

    后续如果接 Web、桌面端或 API 层，这里仍然可以作为统一入口复用。
    """

    config = config or Config.from_env()
    llm = LLMClient(
        model_registry=config.model_registry,
        default_model=config.model_alias,
    )
    registry = ToolRegistry()
    registry.register(ExecTool(working_dir=config.workspace))
    thread_stores = ThreadStoreManager(config.sessions_dir)
    return AppService(config=config, llm=llm, registry=registry, thread_stores=thread_stores)
