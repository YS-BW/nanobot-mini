"""BananaBot CLI 入口"""

import asyncio
import signal
import sys
from datetime import datetime
from typing import Callable

from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.text import Text

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


class ProgressBox:
    """滚动进度显示框"""

    def __init__(self, console: Console):
        self.console = console
        self.lines: list[str] = []
        self._live: Live | None = None

    def add(self, text: str):
        """添加一行"""
        self.lines.append(text)
        # 保持最多 20 行
        if len(self.lines) > 20:
            self.lines.pop(0)

    def clear(self):
        """清空"""
        self.lines.clear()

    def _render(self) -> Panel:
        """渲染面板"""
        if not self.lines:
            return Panel(
                Text("等待中...", style="dim"),
                title="[yellow]🍌 BananaBot 思考中[/yellow]",
                border_style="cyan",
            )
        content = "\n".join(self.lines)
        return Panel(
            Text(content, style="white"),
            title="[cyan]执行过程[/cyan]",
            border_style="cyan",
        )

    def start(self):
        """开始实时显示"""
        self._live = Live(
            self._render(),
            console=self.console,
            auto_refresh=0.1,
            transient=False,
        )
        self._live.start()

    def update(self):
        """更新显示"""
        if self._live:
            self._live.update(self._render())

    def stop(self):
        """停止显示"""
        if self._live:
            self._live.stop()
            self._live = None


async def chat_once(
    llm: LLM,
    registry: ToolRegistry,
    ctx_builder: ContextBuilder,
    session,
    user_message: str,
    max_iterations: int,
    max_history: int = 20,
    progress_callback: Callable[[str], None] | None = None,
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
        progress_callback: 进度回调函数

    Returns:
        AI 回复内容
    """
    history = session.history()[-max_history:]
    messages = ctx_builder.build_messages(history, user_message)

    runner = AgentRunner(llm, registry, max_iterations=max_iterations)
    response = await runner.run(messages, progress_callback=progress_callback)

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
    console.print("[bold yellow]🍌 BananaBot[/bold yellow] 交互模式")
    console.print("命令: /new 新会话, /session <name> 切换会话, /clear 清空, /sessions 列出, /help 帮助, /exit 退出")
    console.print()

    llm, registry, ctx_builder, sessions = _create_runner(config)
    session = sessions.get_or_create("cli:default")

    console.print("🍌 我是 BananaBot，有啥需要帮忙的尽管说！输入 /help 查看命令列表。\n")

    while True:
        try:
            user_message = input("\n你: ").strip()
            if not user_message:
                continue

            # 处理命令
            cmd = user_message.lower()
            if cmd.startswith("/session "):
                target = cmd[9:].strip()
                if target:
                    session = sessions.get_or_create(target)
                    console.print(f"[green]已切换到会话: {session.key}[/green]")
                else:
                    console.print("[yellow]请指定会话名称，如: /session mychat[/yellow]")
                continue

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
                console.print("  /new              - 开启新会话")
                console.print("  /session <name>   - 切换到指定会话")
                console.print("  /clear            - 清空当前会话历史")
                console.print("  /sessions         - 列出所有会话")
                console.print("  /status           - 显示当前状态")
                console.print("  /help             - 显示此帮助")
                console.print("  /exit             - 退出程序")
                continue

            # 正常对话 - 显示进度框
            progress = ProgressBox(console)
            progress.start()

            def on_progress(msg: str):
                progress.add(msg)
                progress.update()

            try:
                reply = await chat_once(
                    llm,
                    registry,
                    ctx_builder,
                    session,
                    user_message,
                    config.max_iterations,
                    progress_callback=on_progress,
                )
            finally:
                progress.stop()

            console.print(f"[yellow]🍌 BananaBot:[/yellow] {reply}")

        except KeyboardInterrupt:
            console.print("\n\n[yellow]再见![/yellow]")
            break


def main():
    """同步入口，供 console script 调用"""
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
            await interactive_mode(config)
        else:
            user_message = " ".join(sys.argv[1:])
            llm, registry, ctx_builder, sessions = _create_runner(config)
            session = sessions.get_or_create("cli:default")

            progress = ProgressBox(console)
            progress.start()

            def on_progress(msg: str):
                progress.add(msg)
                progress.update()

            try:
                reply = await chat_once(
                    llm,
                    registry,
                    ctx_builder,
                    session,
                    user_message,
                    config.max_iterations,
                    progress_callback=on_progress,
                )
            finally:
                progress.stop()

            console.print(f"[yellow]🍌 BananaBot:[/yellow] {reply}")
    except KeyboardInterrupt:
        console.print("\n\n[yellow]再见![/yellow]")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n再见!")
