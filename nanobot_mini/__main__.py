"""BananaBot CLI 入口"""

import asyncio
import json
import signal
import sys
from datetime import datetime
from typing import Callable

from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.status import Status
from rich.text import Text

from .llm import LLM
from .tools import ToolRegistry, ExecTool
from .memory import MemoryStore
from .session import SessionManager, CompactService
from .context import build_context
from .runner import AgentRunner
from .config import Config


def _create_runner(config: Config) -> tuple[LLM, ToolRegistry, SessionManager]:
    """创建 Agent 运行所需的组件"""
    llm = LLM(base_url=config.base_url, api_key=config.api_key, model=config.model)
    registry = ToolRegistry()
    registry.register(ExecTool(working_dir=config.workspace))
    sessions = SessionManager(sessions_dir=config.sessions_dir)
    return llm, registry, sessions


class ProgressBox:
    """滚动进度显示框"""

    def __init__(self, console: Console):
        self.console = console
        self.lines: list[str] = []
        self._live: Live | None = None

    def add(self, text: str):
        """添加一行"""
        self.lines.append(text)
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
    session,
    llm: LLM,
    registry: ToolRegistry,
    user_message: str,
    max_iterations: int,
    config: Config,
    progress_callback: Callable[[str], None] | None = None,
) -> str:
    """
    单次对话处理

    Args:
        session: 会话实例
        llm: LLM 实例
        registry: 工具注册表
        user_message: 用户输入
        max_iterations: 最大迭代次数
        config: 配置
        progress_callback: 进度回调函数

    Returns:
        AI 回复内容
    """
    # 1. 写入当前输入（自动持久化）
    session.add("user", user_message)
    session.append_history([{"role": "user", "content": user_message}])

    # 2. 构建上下文
    messages = build_context(session)

    # 3. 调试日志
    _write_debug_log(session, messages)

    # 4. 记录当前消息数（用于后续提取新增的 assistant/tool 消息）
    msg_count_before = len(messages)

    # 5. Agent 执行
    runner = AgentRunner(llm, registry, max_iterations=max_iterations)
    response = await runner.run(messages, progress_callback=progress_callback)

    # 6. 保存响应（assistant 响应和 tool 结果）
    for msg in messages[msg_count_before:]:
        if msg["role"] in ("assistant", "tool"):
            session.add(msg["role"], msg.get("content", ""))
            session.append_history([{"role": msg["role"], "content": msg.get("content", "")}])

    # 7. 自动 compact
    compact_svc = CompactService(session, llm, config)
    await compact_svc.run_if_needed()

    return response.content or "[无回复内容]"


def _write_debug_log(session, messages):
    """写入调试日志"""
    if session.session_path:
        debug_log = session.session_path.parent / "debug.json"
        debug_log.parent.mkdir(parents=True, exist_ok=True)
        simplified = [
            {"role": m.get("role"), "content": m.get("content")}
            for m in messages
        ]
        with open(debug_log, "w", encoding="utf-8") as f:
            json.dump(simplified, f, ensure_ascii=False, indent=2)


async def interactive_mode(config: Config):
    """交互模式：循环输入输出"""
    console = Console()
    console.print("[bold yellow]🍌 BananaBot[/bold yellow] 交互模式")
    console.print("命令: /new 新会话, /session <name> 切换会话, /clear 清空, /sessions 列出, /compact 压缩会话, /banana 查看指令, /help 帮助, /exit 退出")
    console.print()

    llm, registry, sessions = _create_runner(config)
    session = sessions.get_or_create("cli:default")

    console.print("🍌 我是 BananaBot，有啥需要帮忙的尽管说！输入 /help 查看命令列表。\n")

    while True:
        try:
            user_message = input("\n你: ").strip()
            if not user_message:
                continue

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
                session = sessions.get_or_create(f"cli:{datetime.now().strftime('%Y%m%d%H%M%S')}")
                console.print("[green]已开启新会话[/green]")
                continue

            if cmd == "/clear":
                session.clear()
                console.print("[green]已清空当前会话历史[/green]")
                continue

            if cmd == "/sessions":
                session_list = sessions.list_sessions()
                console.print(f"\n已有会话 ({len(session_list)}):")
                for s in session_list:
                    console.print(f"  - {s}")
                continue

            if cmd == "/status":
                _show_status(console, session, config)
                continue

            if cmd == "/compact":
                await _do_compact(console, session, llm, config)
                continue

            if cmd == "/banana":
                _show_banana(console, config)
                continue

            if cmd == "/help":
                _show_help(console)
                continue

            # 正常对话
            progress = ProgressBox(console)
            progress.start()

            def on_progress(msg: str):
                progress.add(msg)
                progress.update()

            try:
                reply = await chat_once(
                    session=session,
                    llm=llm,
                    registry=registry,
                    user_message=user_message,
                    max_iterations=config.max_iterations,
                    config=config,
                    progress_callback=on_progress,
                )
            finally:
                progress.stop()

            console.print(f"[yellow]🍌 BananaBot:[/yellow] {reply}")

        except KeyboardInterrupt:
            console.print("\n\n[yellow]再见![/yellow]")
            break


def _show_status(console: Console, session, config):
    """显示状态"""
    console.print(f"\n当前会话: {session.key}")
    console.print(f"消息数量: {len(session.messages)}")
    console.print(f"工作目录: {config.workspace}")
    console.print(f"模型: {config.model}")

    if session.session_path:
        console.print(f"\n[cyan]会话文件:[/cyan]")
        console.print(f"  session: {session.session_path}")
        console.print(f"  history: {session.history_path}")
        console.print(f"  summary: {session.summary_path}")
        console.print(f"  memory: {session.memory_path}")

        history_lines = 0
        if session.history_path and session.history_path.exists():
            with open(session.history_path) as f:
                history_lines = sum(1 for _ in f)

        summary_lines = session.get_summary_count()
        has_mem = session.has_memory()

        console.print(f"  history 条目: {history_lines}")
        console.print(f"  summary 条目: {summary_lines}")
        console.print(f"  memory: {'存在' if has_mem else '无'}")


async def _do_compact(console: Console, session, llm, config):
    """执行 compact"""
    try:
        with Status("[cyan]🍌 Compact 中...[/cyan]", console=console):
            compact_svc = CompactService(session, llm, config)
            did_compact = await compact_svc.run_if_needed(force=True)

            if not did_compact:
                console.print("[yellow]无需压缩[/yellow]")
                return

            summary_count = session.get_summary_count()
            has_memory = session.has_memory()

        console.print(f"[green]✓ Compact 完成[/green]")
        if has_memory:
            console.print("  - 已整合到 MEMORY.md")
        else:
            console.print(f"  - 摘要已保存（当前 {summary_count} 条）")

    except Exception as e:
        console.print(f"[red]压缩失败: {e}[/red]")


def _show_banana(console: Console, config: Config):
    """显示 BANANA.md"""
    global_banana = config.global_dir / "BANANA.md"
    project_banana = MemoryStore.find_banana_md(config.workspace)
    console.print(f"\n[cyan]全局指令:[/cyan] {global_banana}")
    if global_banana.exists():
        console.print(global_banana.read_text(encoding="utf-8")[:500])
    else:
        console.print("[dim]暂无全局指令[/dim]")
    console.print(f"\n[cyan]项目指令:[/cyan] {project_banana if project_banana else '无'}")
    if project_banana and project_banana.exists():
        console.print(project_banana.read_text(encoding="utf-8")[:500])
    console.print("\n用法: 编辑 ~/.bananabot/BANANA.md 添加全局指令")
    console.print("      在项目目录添加 BANANA.md 添加项目指令")


def _show_help(console: Console):
    """显示帮助"""
    console.print("\n可用命令:")
    console.print("  /new              - 开启新会话")
    console.print("  /session <name>   - 切换到指定会话")
    console.print("  /clear            - 清空当前会话历史")
    console.print("  /sessions         - 列出所有会话")
    console.print("  /status           - 显示当前状态")
    console.print("  /compact          - 压缩当前会话到历史")
    console.print("  /banana           - 查看全局/项目指令")
    console.print("  /help             - 显示此帮助")
    console.print("  /exit             - 退出程序")


def main():
    """同步入口"""
    def _handle_sigint(*_):
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
            llm, registry, sessions = _create_runner(config)
            session = sessions.get_or_create("cli:default")

            progress = ProgressBox(console)
            progress.start()

            def on_progress(msg: str):
                progress.add(msg)
                progress.update()

            try:
                reply = await chat_once(
                    session=session,
                    llm=llm,
                    registry=registry,
                    user_message=user_message,
                    max_iterations=config.max_iterations,
                    config=config,
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
