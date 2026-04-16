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
    # 重新加载 session，确保 session.messages 与文件一致
    session.reload()

    history = session.history()[-max_history:]
    messages = ctx_builder.build_messages(history, user_message, session=session)

    # 调试日志：写入发送给模型的完整上下文
    import json
    from datetime import datetime
    if session.session_path:
        debug_log = session.session_path.parent / "debug.json"
        debug_log.parent.mkdir(parents=True, exist_ok=True)
        with open(debug_log, "w", encoding="utf-8") as f:
            # 只记录 messages 列表，就是给模型看的内容
            json.dump({
                "timestamp": datetime.now().isoformat(),
                "user_input": user_message,
                "messages": messages
            }, f, ensure_ascii=False, indent=2)

    # 记录当前消息长度，用于只保存本轮新增的消息
    msg_count_before = len(messages)

    runner = AgentRunner(llm, registry, max_iterations=max_iterations)
    response = await runner.run(messages, progress_callback=progress_callback)

    # 保存本轮对话：当前 user 消息（在 msg_count_before-1）+ runner 新增的消息
    current_user_idx = msg_count_before - 1
    if current_user_idx >= 1 and messages[current_user_idx]["role"] == "user":
        session.add(messages[current_user_idx]["role"], messages[current_user_idx].get("content", ""))

    # 保存 runner 新增的消息（从 msg_count_before 开始）
    for msg in messages[msg_count_before:]:
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

    # 自动 compact：检查 token 是否超过阈值
    threshold_tokens = int(config.context_window * config.compact_threshold_round1)
    if session.estimate_tokens() > threshold_tokens:
        trimmed, _ = session.compact(config.context_window, config.compact_threshold_round1)
        if trimmed:
            session.append_history(trimmed)
            summary_prompt = "\n".join(f"[{m['role']}] {m.get('content', '')[:200]}" for m in trimmed)
            summary_response = await llm.chat(
                messages=[{"role": "user", "content": f"总结以下对话要点：\n{summary_prompt}"}],
                tools=None,
            )
            if summary_response.content:
                session.append_summary(summary_response.content)
            # compact() 内部已经 save()，这里不需要再次 save

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
                history = session.history()

                # 检查 token 是否超过阈值
                threshold_tokens = int(config.context_window * config.compact_threshold_round1)
                if session.estimate_tokens() <= threshold_tokens:
                    console.print("[yellow]消息太少，无需压缩[/yellow]")
                    continue

                # 构建 compact 提示词
                compact_prompt = f"""你是一个会话压缩助手。请从以下对话历史中提取关键信息。

对话历史：
{chr(10).join(f"[{msg['role']}] {msg.get('content', '')[:300]}" for msg in history)}

请总结：
1. 用户的主要需求和意图
2. 关键技术信息（模块、文件、配置）
3. 重要决策和结论
4. 发现的 bug 和解决方案
5. 待完成的事项

用简洁的条目形式返回，不超过 500 字。"""

                try:
                    # 第一轮 Compact
                    with Status("[cyan]🍌 第一轮 Compact 中...[/cyan]", console=console) as status:
                        status.update("[cyan]🍌 分析会话历史...[/cyan]")
                        response = await llm.chat(
                            messages=[{"role": "user", "content": compact_prompt}],
                            tools=None,
                        )
                        summary = response.content or ""

                        if not summary.strip():
                            console.print("[yellow]无需更新[/yellow]")
                            continue

                        status.update("[cyan]🍌 裁剪会话...[/cyan]")
                        # 获取被裁剪的消息（保留最近 20 条）
                        trimmed, _ = session.compact()

                        status.update("[cyan]🍌 保存历史...[/cyan]")
                        # 写入 history.jsonl
                        if trimmed:
                            session.append_history(trimmed)

                        # 写入 summary.jsonl
                        session.append_summary(summary)

                        # 保存 session.jsonl
                        session.save()

                        # 检查是否需要第二轮：summary token 超过 context_window * 0.85
                        summary_tokens = session.estimate_summary_tokens()
                        threshold_round2 = int(config.context_window * config.compact_threshold_round2)
                        need_round2 = summary_tokens > threshold_round2

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
                        console.print(f"  - 摘要已保存（当前 {summary_tokens} tokens，阈值 {threshold_round2} tokens）")
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
