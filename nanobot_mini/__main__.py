"""nanobot-mini CLI 入口"""

import asyncio
import signal
import sys
from datetime import datetime

from rich.console import Console

from .llm import LLM
from .tools import ToolRegistry, ExecTool
from .context import ContextBuilder
from .session import SessionManager
from .runner import AgentRunner
from .config import Config


def _create_runner(config: Config) -> tuple[LLM, ToolRegistry, ContextBuilder, SessionManager]:
    """创建 Agent 运行所需的组件"""
    llm = LLM(base_url=config.base_url, api_key=config.api_key, model=config.model)
    registry = ToolRegistry()
    registry.register(ExecTool(working_dir=config.workspace))
    ctx_builder = ContextBuilder(workspace=config.workspace)
    sessions = SessionManager(workspace=config.workspace)
    return llm, registry, ctx_builder, sessions


async def chat_once(
    llm: LLM,
    registry: ToolRegistry,
    ctx_builder: ContextBuilder,
    session,
    user_message: str,
    max_iterations: int,
    max_history: int = 20,
) -> str:
    """
    单次对话处理

    Args:
        llm: LLM 实例
        registry: 工具注册表
        ctx_builder: 上下文构建器
        session: 会话实例
        user_message: 用户输入
        max_iterations: 最大迭代次数
        max_history: 保留的历史消息数量

    Returns:
        AI 回复内容
    """
    history = session.history()[-max_history:]
    messages = ctx_builder.build_messages(history, user_message)

    runner = AgentRunner(llm, registry, max_iterations=max_iterations)
    response = await runner.run(messages)

    # 保存对话历史（跳过 system prompt）
    for msg in messages[1:]:
        if msg["role"] in ("user", "assistant"):
            session.add(msg["role"], msg.get("content", ""))
        elif msg["role"] == "tool":
            session.messages.append({
                "role": "tool",
                "content": msg.get("content", ""),
                "tool_call_id": msg.get("tool_call_id", ""),
                "name": msg.get("name", ""),
                "timestamp": datetime.now().isoformat(),
            })
    session.save()

    return response.content or "[无回复内容]"


async def interactive_mode(config: Config):
    """交互模式：循环输入输出"""
    console = Console()
    console.print("[bold cyan]nanobot-mini[/bold cyan] 交互模式")
    console.print("命令: /new 新会话, /clear 清空, /sessions 列出, /help 帮助, /exit 退出")
    console.print()

    llm, registry, ctx_builder, sessions = _create_runner(config)
    session = sessions.get_or_create("cli:default")

    console.print("欢迎使用 nanobot-mini！输入 /help 查看命令列表。\n")

    while True:
        try:
            user_message = input("\n你: ").strip()
            if not user_message:
                continue

            # 处理命令
            cmd = user_message.lower()
            if cmd in ("exit", "quit", "q"):
                console.print("[yellow]再见![/yellow]")
                break

            if cmd == "/new":
                session = sessions.get_or_create(
                    f"cli:{datetime.now().strftime('%Y%m%d%H%M%S')}"
                )
                console.print("[green]已开启新会话[/green]")
                continue

            if cmd == "/clear":
                session.clear()
                session.save()
                console.print("[green]已清空当前会话历史[/green]")
                continue

            if cmd == "/sessions":
                session_list = sessions.list_sessions()
                console.print(f"\n已有会话 ({len(session_list)}):")
                for s in session_list:
                    console.print(f"  - {s}")
                continue

            if cmd == "/status":
                history_count = len(session.history())
                console.print(f"\n当前会话: {session.key}")
                console.print(f"消息数量: {history_count}")
                console.print(f"工作目录: {config.workspace}")
                console.print(f"模型: {config.model}")
                continue

            if cmd == "/help":
                console.print("\n可用命令:")
                console.print("  /new        - 开启新会话")
                console.print("  /clear     - 清空当前会话历史")
                console.print("  /sessions  - 列出所有会话")
                console.print("  /status    - 显示当前状态")
                console.print("  /help      - 显示此帮助")
                console.print("  /exit      - 退出程序")
                continue

            # 正常对话 - 显示思考动画
            console.print()
            with console.status("[dim]nanobot 思考中...[/dim]", spinner="dots"):
                reply = await chat_once(
                    llm,
                    registry,
                    ctx_builder,
                    session,
                    user_message,
                    config.max_iterations,
                )
            console.print(f"[cyan]nanobot:[/cyan] {reply}")

        except KeyboardInterrupt:
            console.print("\n\n[yellow]再见![/yellow]")
            break


def main():
    """同步入口，供 console script 调用"""
    # 注册信号处理器
    def _handle_sigint(_signum, _frame):
        print("\nGoodbye!")
        sys.exit(0)
    signal.signal(signal.SIGINT, _handle_sigint)

    asyncio.run(_main())


async def _main():
    """异步主函数"""
    config = Config.from_env()
    console = Console()

    try:
        if len(sys.argv) < 2:
            # 交互模式
            await interactive_mode(config)
        else:
            # 单次模式
            user_message = " ".join(sys.argv[1:])
            llm, registry, ctx_builder, sessions = _create_runner(config)
            session = sessions.get_or_create("cli:default")

            with console.status("[dim]nanobot 思考中...[/dim]", spinner="dots"):
                reply = await chat_once(
                    llm,
                    registry,
                    ctx_builder,
                    session,
                    user_message,
                    config.max_iterations,
                )
            console.print(f"[cyan]nanobot:[/cyan] {reply}")
    except KeyboardInterrupt:
        console.print("\n\n[yellow]再见![/yellow]")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n再见!")
