"""python -m nanobot_mini "你好" 入口"""
import asyncio
import signal
import sys
from datetime import datetime

from .llm import LLM
from .tools import ToolRegistry, ExecTool
from .context import ContextBuilder
from .session import SessionManager
from .runner import AgentRunner
from .config import Config


def _setup_signal_handler():
    """注册进程级信号处理器，收到 Ctrl+C 时直接退出"""
    def _handle_sigint(signum, frame):
        print("\nGoodbye!")
        sys.exit(0)
    signal.signal(signal.SIGINT, _handle_sigint)


async def chat_once(llm, registry, ctx_builder, session, user_message: str, max_iterations: int, max_history: int = 20) -> str:
    """单次对话，返回回复内容"""
    history = session.history()[-max_history:]  # 只保留最近 N 条历史
    messages = ctx_builder.build_messages(history, user_message)

    runner = AgentRunner(llm, registry, max_iterations=max_iterations)
    response = await runner.run(messages)

    # 保存对话历史（跳过 system prompt）
    for msg in messages[1:]:  # 跳过 system
        if msg["role"] in ("user", "assistant"):
            session.add(msg["role"], msg.get("content", ""))
        elif msg["role"] == "tool":
            # 工具消息需要保存 tool_call_id 和 name
            session.messages.append({
                "role": "tool",
                "content": msg.get("content", ""),
                "tool_call_id": msg.get("tool_call_id", ""),
                "name": msg.get("name", ""),
                "timestamp": datetime.now().isoformat(),
            })
    session.save()

    return response.content or "[No content]"


async def interactive_mode(config: Config):
    """交互模式：循环输入输出"""
    print("=" * 50)
    print("nanobot-mini 交互模式 (输入 exit 或 Ctrl+C 退出)")
    print("=" * 50)

    # 初始化组件
    llm = LLM(base_url=config.base_url, api_key=config.api_key, model=config.model)
    registry = ToolRegistry()
    registry.register(ExecTool(working_dir=config.workspace))
    ctx_builder = ContextBuilder(workspace=config.workspace)
    sessions = SessionManager(workspace=config.workspace)
    session = sessions.get_or_create("cli:default")

    while True:
        try:
            user_message = input("\n你: ").strip()
            if not user_message:
                continue
            if user_message.lower() in ("exit", "quit", "q"):
                print("再见!")
                break
            if user_message.lower() == "/new":
                session = sessions.get_or_create(f"cli:{datetime.now().strftime('%Y%m%d%H%M%S')}")
                print("已开启新会话，历史已清空")
                continue
            if user_message.lower() == "/clear":
                session.messages.clear()
                session.save()
                print("当前会话历史已清空")
                continue
            if user_message.lower() == "/help":
                print("\n命令列表:")
                print("  /new    - 开启新会话（清空当前历史）")
                print("  /clear  - 清空当前会话历史")
                print("  /help   - 显示此帮助")
                print("  /exit   - 退出")
                continue

            print("\nnanobot: ", end="", flush=True)
            sys.stdout.flush()
            reply = await chat_once(llm, registry, ctx_builder, session, user_message, config.max_iterations)
            print(reply)
            sys.stdout.flush()

        except KeyboardInterrupt:
            print("\n\n再见!")
            break


def main():
    """同步入口，供 console script 调用"""
    _setup_signal_handler()
    asyncio.run(_main())


async def _main():
    config = Config.from_env()

    try:
        if len(sys.argv) < 2:
            # 交互模式
            await interactive_mode(config)
        else:
            # 单次模式
            user_message = " ".join(sys.argv[1:])
            await chat_once(
                LLM(base_url=config.base_url, api_key=config.api_key, model=config.model),
                ToolRegistry(),
                ContextBuilder(workspace=config.workspace),
                SessionManager(workspace=config.workspace).get_or_create("cli:default"),
                user_message,
                config.max_iterations,
            )
    except KeyboardInterrupt:
        print("\n\n再见!")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n再见!")
