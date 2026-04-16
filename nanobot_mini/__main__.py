"""BananaBot CLI 入口"""

import asyncio
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
from .context import ContextBuilder
from .memory import MemoryStore
from .session import SessionManager
from .runner import AgentRunner
from .config import Config


def _create_runner(config: Config) -> tuple[LLM, ToolRegistry, ContextBuilder, MemoryStore, SessionManager]:
    """创建 Agent 运行所需的组件"""
    llm = LLM(base_url=config.base_url, api_key=config.api_key, model=config.model)
    registry = ToolRegistry()
    registry.register(ExecTool(working_dir=config.workspace))
    memory_store = MemoryStore(workspace=config.workspace, global_dir=config.global_dir)
    ctx_builder = ContextBuilder(
        workspace=config.workspace,
        global_dir=config.global_dir,
        memory_store=memory_store,
    )
    sessions = SessionManager(sessions_dir=config.sessions_dir)
    return llm, registry, ctx_builder, memory_store, sessions


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
    progress_callback: Callable[[str], None] | None = None,
    config=None,
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
    # 重新加载 session，确保 session.messages 与文件一致
    session.reload()

    # 把当前输入写入 session（session.messages 包含当前输入）
    session.add("user", user_message)
    session.append_history([{"role": "user", "content": user_message}])
    session.save()

    # 构建上下文：拼接 session.messages（包含当前输入）
    messages = ctx_builder.build_messages(session=session)

    # 调试日志：写入实际发送给模型的内容
    import json
    if session.session_path:
        debug_log = session.session_path.parent / "debug.json"
        debug_log.parent.mkdir(parents=True, exist_ok=True)
        # 只保留 role 和 content 字段（实际发送的内容）
        simplified_messages = [
            {"role": m.get("role"), "content": m.get("content")}
            for m in messages
        ]
        with open(debug_log, "w", encoding="utf-8") as f:
            json.dump(simplified_messages, f, ensure_ascii=False, indent=2)

    msg_count_before = len(messages)

    runner = AgentRunner(llm, registry, max_iterations=max_iterations)
    response = await runner.run(messages, progress_callback=progress_callback)

    # 保存本轮新增的对话（assistant 响应和 tool 结果）
    new_msgs = []
    for msg in messages[msg_count_before:]:
        if msg["role"] in ("assistant", "tool"):
            session.add(msg["role"], msg.get("content", ""))
            new_msgs.append({"role": msg["role"], "content": msg.get("content", "")})
    if new_msgs:
        session.append_history(new_msgs)
    session.save()

    # 自动 compact：检查 token 是否超过阈值
    if config and session.estimate_tokens() > int(config.context_window * config.compact_threshold_round1):
        # compact 内部处理裁剪、history 写入、summary 生成、重试
        await session.compact(
            llm,
            config.context_window,
            config.compact_threshold_round1,
        )

        # 检查是否需要第二轮 compact（summary 条数 >= 25）
        if session.get_summary_count() >= 25:
            await session.compact_round2(llm)

    return response.content or "[无回复内容]"


async def interactive_mode(config: Config):
    """交互模式：循环输入输出"""
    console = Console()
    console.print("[bold yellow]🍌 BananaBot[/bold yellow] 交互模式")
    console.print("命令: /new 新会话, /session <name> 切换会话, /clear 清空, /sessions 列出, /compact 压缩会话, /banana 查看指令, /help 帮助, /exit 退出")
    console.print()

    llm, registry, ctx_builder, memory_store, sessions = _create_runner(config)
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

                # 显示 session 目录信息
                if session.session_path:
                    console.print(f"\n[cyan]会话文件:[/cyan]")
                    console.print(f"  session: {session.session_path}")
                    console.print(f"  history: {session.history_path}")
                    console.print(f"  summary: {session.summary_path}")

                    # 统计 history 和 summary
                    history_lines = 0
                    if session.history_path and session.history_path.exists():
                        with open(session.history_path) as f:
                            history_lines = sum(1 for _ in f)

                    summary_lines = 0
                    if session.summary_path and session.summary_path.exists():
                        with open(session.summary_path) as f:
                            summary_lines = sum(1 for _ in f)

                    console.print(f"  history 条目: {history_lines}")
                    console.print(f"  summary 条目: {summary_lines}")
                continue

            if cmd == "/compact":
                # Compact：将 session 压缩到 history.jsonl 和 summary.jsonl
                # 手动触发时强制执行，不检查 token 阈值
                try:
                    with Status("[cyan]🍌 Compact 中...[/cyan]", console=console) as status:
                        # 第一轮 compact（生成 1 条 summary）
                        status.update("[cyan]🍌 裁剪会话...[/cyan]")
                        trimmed, summary = await session.compact(
                            llm,
                            config.context_window,
                            config.compact_threshold_round1,
                            force=True,
                        )

                        if not trimmed:
                            console.print("[yellow]无需压缩[/yellow]")
                            continue

                        # 检查是否需要第二轮（summary 条数 >= 25）
                        summary_count = session.get_summary_count()
                        need_round2 = summary_count >= 25

                        if need_round2:
                            status.update("[cyan]🍌 第二轮 Compact 中...[/cyan]")
                            new_memory = await session.compact_round2(llm)
                            if new_memory:
                                status.update("[cyan]🍌 已更新 MEMORY.md[/cyan]")
                            memory_preview = new_memory
                        else:
                            memory_preview = None

                    console.print(f"[green]✓ Compact 完成[/green]")
                    if need_round2:
                        console.print(f"  - 第一轮：裁剪 {len(trimmed) if trimmed else 0} 条消息")
                        console.print(f"  - 第二轮：已整合到 MEMORY.md")
                        if memory_preview:
                            console.print(f"\n[yellow]MEMORY.md 预览:[/yellow]")
                            console.print(memory_preview[:500] + "..." if len(memory_preview) > 500 else memory_preview)
                    else:
                        console.print(f"  - 裁剪 {len(trimmed) if trimmed else 0} 条消息到历史")
                        console.print(f"  - 摘要已保存（当前 {summary_count} 条）")
                        console.print(f"\n[yellow]摘要预览:[/yellow]")
                        console.print(summary[:500] + "..." if len(summary) > 500 else summary)

                except Exception as e:
                    console.print(f"[red]压缩失败: {e}[/red]")
                continue

            if cmd == "/banana":
                # 全局 BANANA.md
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
                continue

            if cmd == "/help":
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
                    config=config,
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
            llm, registry, ctx_builder, memory_store, sessions = _create_runner(config)
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
                    config=config,
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
