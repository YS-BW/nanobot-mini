"""Stage 1 refactor regression tests."""

import json
import tempfile
import unittest
from pathlib import Path

from textual.widgets import TextArea

from nanobot_mini.app import AppService, ChatRequest
from nanobot_mini.app.cli import BananaTUI
from nanobot_mini.llm import LLMResponse, LLMStreamChunk, ToolCall, ToolCallDelta
from nanobot_mini.memory import CompactService, SessionManager
from nanobot_mini.runtime import build_context
from nanobot_mini.tools import ExecTool, ToolRegistry


class DummyConfig:
    """Minimal config object for isolated tests."""

    def __init__(self, root: Path):
        self.workspace = root
        self.global_dir = root / ".bananabot"
        self.global_dir.mkdir(parents=True, exist_ok=True)
        self.sessions_dir = root / "sessions"
        self.sessions_dir.mkdir(parents=True, exist_ok=True)
        self.base_url = "http://example.invalid"
        self.model = "test-model"
        self.api_key = ""
        self.max_iterations = 5
        self.context_window = 128000
        self.compact_threshold_round1 = 0.70
        self.compact_threshold_round2 = 0.85


class FakeLLM:
    """Queue-based fake LLM for service and compact tests."""

    def __init__(
        self,
        responses: list[LLMResponse] | None = None,
        stream_responses: list[LLMResponse | list[LLMStreamChunk]] | None = None,
    ):
        self.responses = list(responses or [])
        self.stream_responses = list(stream_responses or [])
        self.calls: list[dict] = []

    async def chat(self, messages, tools=None, stream=False):
        self.calls.append({"messages": messages, "tools": tools, "stream": stream})
        if not self.responses:
            raise AssertionError("No fake response left for chat()")
        return self.responses.pop(0)

    async def chat_stream(self, messages, tools=None):
        self.calls.append({"messages": messages, "tools": tools, "stream": True})
        if not self.stream_responses:
            raise AssertionError("No fake response left for chat_stream()")

        item = self.stream_responses.pop(0)
        if isinstance(item, list):
            for chunk in item:
                yield chunk
            return

        if item.content:
            yield LLMStreamChunk(content=item.content)
        for index, tool_call in enumerate(item.tool_calls):
            yield LLMStreamChunk(
                tool_calls=[
                    ToolCallDelta(
                        index=index,
                        id=tool_call.id,
                        name=tool_call.name,
                        arguments_chunk=json.dumps(tool_call.arguments, ensure_ascii=False),
                    )
                ]
            )
        yield LLMStreamChunk(finish_reason=item.finish_reason)


class Stage1RefactorTests(unittest.IsolatedAsyncioTestCase):
    """Regression tests for the stage 1 structure."""

    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        self.config = DummyConfig(self.root)
        self.registry = ToolRegistry()
        self.registry.register(ExecTool(working_dir=self.root))
        self.sessions = SessionManager(self.config.sessions_dir)

    def tearDown(self):
        self.tempdir.cleanup()

    def create_service(
        self,
        responses: list[LLMResponse] | None = None,
        stream_responses: list[LLMResponse | list[LLMStreamChunk]] | None = None,
    ) -> AppService:
        return AppService(
            config=self.config,
            llm=FakeLLM(responses=responses, stream_responses=stream_responses),
            registry=self.registry,
            sessions=self.sessions,
        )

    @staticmethod
    def text_area_text(widget: TextArea) -> str:
        """读取 TextArea 当前纯文本内容。"""

        return widget.text

    async def test_chat_persists_user_and_assistant_messages(self):
        service = self.create_service(
            stream_responses=[
                [
                    LLMStreamChunk(content="你好，"),
                    LLMStreamChunk(content="我在。"),
                    LLMStreamChunk(finish_reason="stop"),
                ]
            ]
        )

        response = await service.chat(ChatRequest(session_id="test:chat", user_input="你好"))

        self.assertEqual(response.message, "你好，我在。")
        session = self.sessions.get_or_create("test:chat")
        self.assertEqual([msg["role"] for msg in session.messages], ["user", "assistant"])
        self.assertTrue(session.session_path.exists())
        self.assertTrue(session.history_path.exists())

        status = service.get_status("test:chat")
        self.assertEqual(status["message_count"], 2)
        self.assertEqual(status["history_count"], 2)

    async def test_chat_stream_emits_tool_events_and_saves_tool_output(self):
        service = self.create_service(
            stream_responses=[
                [
                    LLMStreamChunk(
                        tool_calls=[
                            ToolCallDelta(index=0, id="tool-1", name="exec", arguments_chunk='{"command":"')
                        ]
                    ),
                    LLMStreamChunk(tool_calls=[ToolCallDelta(index=0, arguments_chunk="printf ok")]),
                    LLMStreamChunk(tool_calls=[ToolCallDelta(index=0, arguments_chunk='"}')]),
                    LLMStreamChunk(finish_reason="tool_calls"),
                ],
                [
                    LLMStreamChunk(content="执行"),
                    LLMStreamChunk(content="完成"),
                    LLMStreamChunk(finish_reason="stop"),
                ],
            ]
        )

        events = []
        async for event in service.chat_stream(ChatRequest(session_id="test:tool", user_input="执行命令")):
            events.append(event)

        event_types = [event.type for event in events]
        self.assertIn("assistant_thinking", event_types)
        self.assertIn("assistant_delta", event_types)
        self.assertIn("tool_call_started", event_types)
        self.assertIn("tool_call_finished", event_types)
        self.assertIn("assistant_message", event_types)
        self.assertEqual(event_types[-1], "done")

        session = self.sessions.get_or_create("test:tool")
        self.assertEqual([msg["role"] for msg in session.messages], ["user", "assistant", "tool", "assistant"])
        self.assertIn("ok", session.messages[2]["content"])
        self.assertEqual(session.messages[-1]["content"], "执行完成")

    async def test_chat_stream_emits_incremental_assistant_delta(self):
        service = self.create_service(
            stream_responses=[
                [
                    LLMStreamChunk(content="你"),
                    LLMStreamChunk(content="好"),
                    LLMStreamChunk(content="啊"),
                    LLMStreamChunk(finish_reason="stop"),
                ]
            ]
        )

        deltas = []
        final_message = None
        async for event in service.chat_stream(ChatRequest(session_id="test:delta", user_input="打个招呼")):
            if event.type == "assistant_delta":
                deltas.append((event.data or {}).get("delta"))
            if event.type == "assistant_message":
                final_message = event.message

        self.assertEqual(deltas, ["你", "好", "啊"])
        self.assertEqual(final_message, "你好啊")

    async def test_chat_stream_emits_reasoning_delta(self):
        service = self.create_service(
            stream_responses=[
                [
                    LLMStreamChunk(reasoning_content="先想一下。"),
                    LLMStreamChunk(reasoning_content="这事不复杂。"),
                    LLMStreamChunk(content="直接开干。"),
                    LLMStreamChunk(finish_reason="stop"),
                ]
            ]
        )

        reasoning_deltas = []
        final_message = None
        async for event in service.chat_stream(ChatRequest(session_id="test:reasoning", user_input="你先想一下")):
            if event.type == "assistant_reasoning_delta":
                reasoning_deltas.append((event.data or {}).get("delta"))
            if event.type == "assistant_message":
                final_message = event.message

        self.assertEqual(reasoning_deltas, ["先想一下。", "这事不复杂。"])
        self.assertEqual(final_message, "直接开干。")

    async def test_tui_mounts_and_handles_help_and_chat(self):
        service = self.create_service(
            stream_responses=[
                [
                    LLMStreamChunk(reasoning_content="先想一下。"),
                    LLMStreamChunk(content="你好，我在。"),
                    LLMStreamChunk(finish_reason="stop"),
                ]
            ]
        )
        app = BananaTUI(service)

        async with app.run_test() as pilot:
            await pilot.pause()
            await app._run_command("/help")
            await app._run_chat("你好")
            await pilot.pause()

            main_text = self.text_area_text(app.main_view)

        self.assertIn("❯ /help", main_text)
        self.assertIn("可用命令:", main_text)
        self.assertIn("Thinked", main_text)
        self.assertIn("⏺ 你好，我在。", main_text)
        self.assertIn("Tips for getting started", main_text)
        self.assertIn("Context", main_text)

    async def test_tui_shows_tool_summary_box_when_tools_called(self):
        service = self.create_service(
            stream_responses=[
                [
                    LLMStreamChunk(
                        tool_calls=[
                            ToolCallDelta(index=0, id="tool-1", name="exec", arguments_chunk='{"command":"echo ok"}')
                        ]
                    ),
                    LLMStreamChunk(finish_reason="tool_calls"),
                ],
                [
                    LLMStreamChunk(content="完成"),
                    LLMStreamChunk(finish_reason="stop"),
                ],
            ]
        )
        app = BananaTUI(service)

        async with app.run_test() as pilot:
            await pilot.pause()
            await app._run_chat("执行一下")
            await pilot.pause()

            main_text = self.text_area_text(app.main_view)

        self.assertIn("┌ thinking", main_text)
        self.assertIn("tools", main_text)
        self.assertIn("exec", main_text)
        self.assertIn("⏺ 完成", main_text)

    async def test_tui_thinking_box_respects_dynamic_height(self):
        service = self.create_service(
            stream_responses=[
                [
                    LLMStreamChunk(reasoning_content="短思考。"),
                    LLMStreamChunk(
                        tool_calls=[
                            ToolCallDelta(index=0, id="tool-1", name="exec", arguments_chunk='{"command":"echo ok"}')
                        ]
                    ),
                    LLMStreamChunk(finish_reason="tool_calls"),
                ],
                [
                    LLMStreamChunk(content="完成"),
                    LLMStreamChunk(finish_reason="stop"),
                ],
            ]
        )
        app = BananaTUI(service)

        async with app.run_test() as pilot:
            await pilot.pause()
            await app._run_chat("执行一下")
            await pilot.pause()

            main_text = self.text_area_text(app.main_view)

        self.assertIn("┌ thinking", main_text)
        self.assertNotIn("│                                                                    \n│                                                                    \n│                                                                    ", main_text)

    async def test_thinking_box_can_shrink_after_completion(self):
        service = self.create_service(
            stream_responses=[
                [
                    LLMStreamChunk(
                        reasoning_content="短思考。"
                    ),
                    LLMStreamChunk(
                        tool_calls=[
                            ToolCallDelta(index=0, id="tool-1", name="exec", arguments_chunk='{"command":"echo ok"}')
                        ]
                    ),
                    LLMStreamChunk(finish_reason="tool_calls"),
                ],
                [
                    LLMStreamChunk(content="完成"),
                    LLMStreamChunk(finish_reason="stop"),
                ],
            ]
        )
        app = BananaTUI(service)

        async with app.run_test() as pilot:
            await pilot.pause()
            await app._run_chat("执行一下")
            await pilot.pause()

            main_text = self.text_area_text(app.main_view)

        self.assertIn("│ tools", main_text)
        self.assertIn("│ exec", main_text)
        self.assertNotIn("│ tool: exec", main_text)

    async def test_compact_service_trims_session_and_writes_summary(self):
        fake_llm = FakeLLM([LLMResponse(content="用户提问，模型完成回答")])
        session = self.sessions.get_or_create("test:compact")
        for index in range(30):
            session.add("user", f"message-{index}")
            session.append_history([{"role": "user", "content": f"message-{index}"}])

        compact = CompactService(session=session, llm=fake_llm, config=self.config)
        did_compact = await compact.run_if_needed(force=True)

        self.assertTrue(did_compact)
        self.assertEqual(len(session.messages), 20)
        self.assertEqual(session.get_summary_count(), 1)
        self.assertTrue(session.history_path.exists())
        with open(session.history_path, encoding="utf-8") as handle:
            self.assertEqual(sum(1 for _ in handle), 30)

    async def test_context_builder_prefers_memory_over_summary(self):
        session = self.sessions.get_or_create("test:context")
        session.add("user", "最近做了什么")
        session.append_summary("这是旧摘要")
        session.memory_path.write_text("这是长期记忆", encoding="utf-8")

        messages = build_context(session=session, workspace=self.root)

        self.assertEqual(messages[0]["content"], "这是长期记忆")
        self.assertIn("BananaBot", messages[1]["content"])
        self.assertEqual(messages[-1]["content"], "最近做了什么")


if __name__ == "__main__":
    unittest.main()
