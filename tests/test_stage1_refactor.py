"""Stage 1 refactor regression tests."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from textual.containers import Vertical
from textual.widgets import Input, TextArea

from bananabot.app import AppService, TaskRequest
from bananabot.app.cli import BananaTUI
from bananabot.app.cli_lists import CommandListItem, ModelListItem
from bananabot.infra import Config
from bananabot.llm import (
    LLMResponse,
    LLMStreamChunk,
    ModelCapabilities,
    ModelProfile,
    ProviderFactory,
    ProviderRegistry,
    ToolCall,
    ToolCallDelta,
)
from bananabot.memory import CompactService, ThreadStore, ThreadStoreManager
from bananabot.runtime import TaskRun, ThreadRef, build_context
from bananabot.tools import ExecTool, ToolRegistry


class DummyConfig:
    """Minimal config object for isolated tests."""

    def __init__(self, root: Path):
        self.workspace = root
        self.global_dir = root / ".bananabot"
        self.global_dir.mkdir(parents=True, exist_ok=True)
        self.sessions_dir = root / "sessions"
        self.sessions_dir.mkdir(parents=True, exist_ok=True)
        self.runtime_state_dir = root / "runtime-state"
        self.runtime_state_dir.mkdir(parents=True, exist_ok=True)
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
        self._profiles = [
            ModelProfile(
                alias="test-model",
                provider="test",
                model="test-model",
                base_url="http://example.invalid",
                api_key="",
                capabilities=ModelCapabilities(),
                description="Test Model",
            ),
            ModelProfile(
                alias="local-model",
                provider="local",
                model="local-model",
                base_url="http://127.0.0.1:8000/v1",
                api_key="token",
                capabilities=ModelCapabilities(),
                description="Local Model",
            ),
        ]
        self._current_alias = "test-model"

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

    def list_models(self):
        return self._profiles

    def get_current_profile(self):
        for profile in self._profiles:
            if profile.alias == self._current_alias:
                return profile
        return self._profiles[0]

    def get_model_alias(self):
        return self._current_alias

    def set_model(self, alias_or_model):
        for profile in self._profiles:
            if profile.alias == alias_or_model or profile.model == alias_or_model:
                self._current_alias = profile.alias
                return profile
        raise KeyError(alias_or_model)


class Stage1RefactorTests(unittest.IsolatedAsyncioTestCase):
    """Regression tests for the stage 1 structure."""

    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        self.config = DummyConfig(self.root)
        self.registry = ToolRegistry()
        self.registry.register(ExecTool(working_dir=self.root))
        self.sessions = ThreadStoreManager(self.config.sessions_dir)

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
            thread_stores=self.sessions,
        )

    @staticmethod
    def text_area_text(widget: TextArea) -> str:
        """读取 TextArea 当前纯文本内容。"""

        return widget.text

    async def test_run_task_persists_user_and_assistant_messages(self):
        service = self.create_service(
            stream_responses=[
                [
                    LLMStreamChunk(content="你好，"),
                    LLMStreamChunk(content="我在。"),
                    LLMStreamChunk(finish_reason="stop"),
                ]
            ]
        )

        response = await service.run_task(TaskRequest(thread_id="test:chat", objective="你好"))

        self.assertEqual(response.output, "你好，我在。")
        thread_store = self.sessions.get_or_create_thread("test:chat")
        self.assertEqual([msg["role"] for msg in thread_store.messages], ["user", "assistant"])
        self.assertTrue(thread_store.session_path.exists())
        self.assertTrue(thread_store.history_path.exists())

        status = service.get_thread_status("test:chat")
        self.assertEqual(status["message_count"], 2)
        self.assertEqual(status["history_count"], 2)

    async def test_run_task_stream_emits_tool_events_and_saves_tool_output(self):
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
        async for event in service.run_task_stream(TaskRequest(thread_id="test:tool", objective="执行命令")):
            events.append(event)

        event_types = [event.type for event in events]
        self.assertIn("assistant_thinking", event_types)
        self.assertIn("assistant_delta", event_types)
        self.assertIn("tool_call_started", event_types)
        self.assertIn("tool_call_finished", event_types)
        self.assertIn("assistant_message", event_types)
        self.assertEqual(event_types[-1], "done")

        thread_store = self.sessions.get_or_create_thread("test:tool")
        self.assertEqual([msg["role"] for msg in thread_store.messages], ["user", "assistant", "tool", "assistant"])
        self.assertIn("ok", thread_store.messages[2]["content"])
        self.assertEqual(thread_store.messages[-1]["content"], "执行完成")

    async def test_run_task_stream_emits_incremental_assistant_delta(self):
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
        async for event in service.run_task_stream(TaskRequest(thread_id="test:delta", objective="打个招呼")):
            if event.type == "assistant_delta":
                deltas.append(event.payload.get("delta"))
            if event.type == "assistant_message":
                final_message = event.message

        self.assertEqual(deltas, ["你", "好", "啊"])
        self.assertEqual(final_message, "你好啊")

    async def test_run_task_stream_preserves_runtime_identity_chain(self):
        service = self.create_service(
            stream_responses=[
                [
                    LLMStreamChunk(content="你"),
                    LLMStreamChunk(content="好"),
                    LLMStreamChunk(finish_reason="stop"),
                ]
            ]
        )

        events = []
        async for event in service.run_task_stream(
            TaskRequest(
                thread_id="thread:stable",
                objective="打个招呼",
                task_run_id="task_fixed",
            )
        ):
            events.append(event)

        runtime_events = [event for event in events if event.type != "done"]
        turn_events = [
            event
            for event in runtime_events
            if event.type
            in {
                "turn_started",
                "assistant_thinking",
                "assistant_delta",
                "assistant_message",
                "turn_completed",
            }
        ]
        step_events = [
            event
            for event in runtime_events
            if event.type in {"assistant_thinking", "assistant_delta", "assistant_message"}
        ]

        self.assertTrue(runtime_events)
        self.assertTrue(all(event.thread_id == "thread:stable" for event in runtime_events))
        self.assertTrue(all(event.task_run_id == "task_fixed" for event in runtime_events))
        self.assertTrue(all(event.turn_id for event in turn_events))
        self.assertTrue(all(event.step_id for event in step_events))
        self.assertEqual(events[-1].task_run_id, "task_fixed")
        self.assertEqual(events[-1].thread_id, "thread:stable")

    async def test_run_task_stream_accepts_task_request(self):
        service = self.create_service(
            stream_responses=[
                [
                    LLMStreamChunk(content="直接"),
                    LLMStreamChunk(content="走 task"),
                    LLMStreamChunk(finish_reason="stop"),
                ]
            ]
        )

        final_message = None
        async for event in service.run_task_stream(
            TaskRequest(thread_id="thread:task-mode", objective="直接走 task")
        ):
            if event.type == "assistant_message":
                final_message = event.message

        self.assertEqual(final_message, "直接走 task")
        thread_session = self.sessions.get_or_create_thread("thread:task-mode")
        self.assertEqual([msg["role"] for msg in thread_session.messages], ["user", "assistant"])

    async def test_run_task_persists_runtime_state_files(self):
        service = self.create_service(
            stream_responses=[
                [
                    LLMStreamChunk(content="状态"),
                    LLMStreamChunk(content="已落盘"),
                    LLMStreamChunk(finish_reason="stop"),
                ]
            ]
        )

        events = []
        async for event in service.run_task_stream(
            TaskRequest(thread_id="thread:state", objective="把状态落盘")
        ):
            events.append(event)

        runtime_events = [event for event in events if event.type != "done"]
        turn_ids = {event.turn_id for event in runtime_events if event.turn_id}
        step_ids = {event.step_id for event in runtime_events if event.step_id}

        self.assertTrue((self.config.runtime_state_dir / "threads" / "thread:state.json").exists())
        self.assertTrue((self.config.runtime_state_dir / "event_log.jsonl").exists())
        self.assertEqual(len(turn_ids), 1)
        self.assertGreaterEqual(len(step_ids), 2)
        task_run_id = events[-1].task_run_id
        self.assertTrue((self.config.runtime_state_dir / "task_runs" / f"{task_run_id}.json").exists())
        for turn_id in turn_ids:
            self.assertTrue((self.config.runtime_state_dir / "turns" / f"{turn_id}.json").exists())
        for step_id in step_ids:
            self.assertTrue((self.config.runtime_state_dir / "steps" / f"{step_id}.json").exists())

    async def test_run_task_stream_emits_reasoning_delta(self):
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
        async for event in service.run_task_stream(TaskRequest(thread_id="test:reasoning", objective="你先想一下")):
            if event.type == "assistant_reasoning_delta":
                reasoning_deltas.append(event.payload.get("delta"))
            if event.type == "assistant_message":
                final_message = event.message

        self.assertEqual(reasoning_deltas, ["先想一下。", "这事不复杂。"])
        self.assertEqual(final_message, "直接开干。")

    async def test_tui_mounts_and_handles_help_and_task(self):
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
            await app.command_handler.run("/help")
            await app.conversation_handler.run("你好")
            await pilot.pause()

            main_text = self.text_area_text(app.main_view)

        self.assertIn("❯ /help", main_text)
        self.assertIn("可用命令:", main_text)
        self.assertIn("/threads", main_text)
        self.assertNotIn("/resume", main_text)
        self.assertNotIn("/session <name>", main_text)
        self.assertIn("Thinked", main_text)
        self.assertIn("⏺ 你好，我在。", main_text)
        self.assertIn("Tips for getting started", main_text)
        self.assertIn("Context", main_text)

    async def test_threads_command_opens_inline_picker_and_switches_thread(self):
        service = self.create_service()
        service.get_thread("cli:default").add("user", "默认线程")
        target = service.get_thread("cli:other")
        target.add("user", "切换目标")

        app = BananaTUI(service)

        async with app.run_test() as pilot:
            await pilot.pause()
            await app.command_handler.run("/threads")
            await pilot.pause()

            picker = app.query_one("#thread-picker-inline", Vertical)
            self.assertTrue(picker.has_class("-open"))
            self.assertEqual(app.thread_picker_list.index, 0)

            app.thread_picker_search.value = "other"
            app._refresh_thread_picker("other")
            await pilot.pause()
            await app.on_input_submitted(Input.Submitted(app.thread_picker_search, app.thread_picker_search.value))
            await pilot.pause()

        self.assertEqual(app.thread_store.key, "cli:other")
        self.assertFalse(picker.has_class("-open"))

    async def test_thread_picker_enter_without_match_reports_and_closes(self):
        service = self.create_service()
        thread_store = service.get_thread("cli:default")
        thread_store.add("user", "默认线程")

        app = BananaTUI(service)

        async with app.run_test() as pilot:
            await pilot.pause()
            await app.command_handler.run("/threads")
            await pilot.pause()

            app.thread_picker_search.value = "not-found"
            app._refresh_thread_picker("not-found")
            await pilot.pause()
            await app.on_input_submitted(Input.Submitted(app.thread_picker_search, app.thread_picker_search.value))
            await pilot.pause()

            main_text = self.text_area_text(app.main_view)
            picker_open = app.thread_picker.has_class("-open")

        self.assertIn("没有匹配的线程", main_text)
        self.assertFalse(picker_open)

    async def test_thread_picker_supports_arrow_navigation_and_escape(self):
        service = self.create_service()
        service.get_thread("cli:default").add("user", "默认线程")
        service.get_thread("cli:alpha").add("user", "alpha")
        service.get_thread("cli:beta").add("user", "beta")

        app = BananaTUI(service)

        async with app.run_test() as pilot:
            await pilot.pause()
            await app.command_handler.run("/threads")
            await pilot.pause()

            self.assertTrue(app.thread_picker.has_class("-open"))
            first_entry = app._current_thread_entry()

            await pilot.press("down")
            await pilot.pause()
            second_entry = app._current_thread_entry()

            self.assertIsNotNone(first_entry)
            self.assertIsNotNone(second_entry)
            self.assertNotEqual(first_entry.thread_id, second_entry.thread_id)

            await pilot.press("escape")
            await pilot.pause()

            self.assertFalse(app.thread_picker.has_class("-open"))
            self.assertIs(app.focused, app.input_bar)

    async def test_slash_input_shows_command_picker(self):
        service = self.create_service()
        app = BananaTUI(service)

        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("/")
            await pilot.pause()

            picker = app.command_picker
            picker_text = "\n".join(
                item.entry.command for item in app.command_picker_list.query(CommandListItem)
            )

        self.assertTrue(picker.has_class("-open"))
        self.assertIn("/help", picker_text)
        self.assertIn("/threads", picker_text)
        self.assertIn("/compact", picker_text)

    async def test_command_picker_enter_executes_selected_command(self):
        service = self.create_service()
        app = BananaTUI(service)

        async with app.run_test() as pilot:
            await pilot.pause()
            app.input_bar.value = "/sta"
            app._refresh_command_picker("/sta")
            await pilot.pause()

            await app.on_input_submitted(Input.Submitted(app.input_bar, app.input_bar.value))
            await pilot.pause()
            input_value = app.input_bar.value
            picker_open = app.command_picker.has_class("-open")
            main_text = self.text_area_text(app.main_view)

        self.assertEqual(input_value, "")
        self.assertFalse(picker_open)
        self.assertIn("当前线程:", main_text)

    async def test_model_command_opens_inline_picker_and_switches_model(self):
        service = self.create_service()
        app = BananaTUI(service)

        async with app.run_test() as pilot:
            await pilot.pause()
            await app.command_handler.run("/model")
            await pilot.pause()

            picker = app.model_picker
            picker_text = "\n".join(item.entry.alias for item in app.model_picker_list.query(ModelListItem))
            picker_detail_text = "\n".join(
                item.entry.subtitle for item in app.model_picker_list.query(ModelListItem)
            )
            self.assertTrue(picker.has_class("-open"))
            self.assertIn("test-model", picker_text)
            self.assertIn("local-model", picker_text)
            self.assertIn("stream:y", picker_detail_text)
            self.assertIn("tools:y", picker_detail_text)

            await pilot.press("down")
            await pilot.pause()
            await app.on_input_submitted(Input.Submitted(app.input_bar, ""))
            await pilot.pause()

            main_text = self.text_area_text(app.main_view)

        self.assertIn("已切换模型 local-model", main_text)
        self.assertIn("provider: local", main_text)
        self.assertIn("capabilities: stream:y", main_text)
        self.assertEqual(service.llm.get_model_alias(), "local-model")

    def test_config_prefers_models_toml_and_uses_env_keys(self):
        env_path = self.root / ".env"
        env_path.write_text(
            "\n".join(
                [
                    "DASHSCOPE_API_KEY=test-dash",
                    "DEFAULT_MODEL=demo-model",
                    "CONTEXT_WINDOW=8192",
                ]
            ),
            encoding="utf-8",
        )
        models_path = self.root / "models.toml"
        models_path.write_text(
            "\n".join(
                [
                    "[meta]",
                    'default_model = "demo-model"',
                    "",
                    "[models.demo]",
                    'alias = "demo-model"',
                    'provider = "dashscope"',
                    'model = "qwen-demo"',
                    'base_url = "https://example.com/v1"',
                    'api_key_env = "DASHSCOPE_API_KEY"',
                    'description = "Demo Model"',
                    "reasoning = true",
                ]
            ),
            encoding="utf-8",
        )

        with patch.dict("os.environ", {}, clear=True), patch(
            "bananabot.infra.config.find_env_file", return_value=env_path
        ), patch("bananabot.infra.config.find_models_file", return_value=models_path):
            config = Config.from_env()

        profiles = config.model_registry.list_profiles()
        self.assertEqual(len(profiles), 1)
        self.assertEqual(profiles[0].alias, "demo-model")
        self.assertEqual(profiles[0].api_key, "test-dash")
        self.assertTrue(profiles[0].capabilities.supports_reasoning)

    def test_provider_registry_maps_known_backends(self):
        registry = ProviderRegistry()

        self.assertEqual(registry.get("dashscope").backend, "dashscope")
        self.assertEqual(registry.get("deepseek").backend, "openai_compat")
        self.assertEqual(registry.get("minimax").backend, "openai_compat")

    def test_provider_factory_resolves_backend_provider(self):
        factory = ProviderFactory()

        dashscope_provider = factory.create(
            ModelProfile(
                alias="qwen-test",
                provider="dashscope",
                backend="dashscope",
                model="qwen-test",
                base_url="https://example.com/v1",
            )
        )
        compat_provider = factory.create(
            ModelProfile(
                alias="deepseek-test",
                provider="deepseek",
                backend="openai_compat",
                model="deepseek-test",
                base_url="https://example.com/v1",
            )
        )

        self.assertEqual(dashscope_provider.__class__.__name__, "DashScopeProvider")
        self.assertEqual(compat_provider.__class__.__name__, "OpenAICompatProvider")

    async def test_direct_model_command_switches_model(self):
        service = self.create_service()
        app = BananaTUI(service)

        async with app.run_test() as pilot:
            await pilot.pause()
            await app.command_handler.run("/model local-model")
            await pilot.pause()

            main_text = self.text_area_text(app.main_view)

        self.assertIn("已切换模型 local-model", main_text)
        self.assertIn("provider: local", main_text)
        self.assertEqual(service.llm.get_model_alias(), "local-model")

    async def test_command_picker_supports_arrow_navigation(self):
        service = self.create_service()
        app = BananaTUI(service)

        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("/")
            await pilot.pause()

            first_entry = app._current_command_entry()
            await pilot.press("down")
            await pilot.pause()
            second_entry = app._current_command_entry()

        self.assertIsNotNone(first_entry)
        self.assertIsNotNone(second_entry)
        self.assertNotEqual(first_entry.command, second_entry.command)

    async def test_thread_entries_sort_by_latest_mtime(self):
        service = self.create_service()
        older = service.get_thread("cli:older")
        older.add("user", "旧线程")
        newer = service.get_thread("cli:newer")
        newer.add("user", "新线程")

        app = BananaTUI(service)
        entries = app.build_thread_entries()

        self.assertGreaterEqual(len(entries), 2)
        self.assertEqual(entries[0].thread_id, "cli:newer")

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
            await app.conversation_handler.run("执行一下")
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
            await app.conversation_handler.run("执行一下")
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
            await app.conversation_handler.run("执行一下")
            await pilot.pause()

            main_text = self.text_area_text(app.main_view)

        self.assertIn("│ tools", main_text)
        self.assertIn("│ exec", main_text)
        self.assertNotIn("│ tool: exec", main_text)

    async def test_compact_service_trims_thread_and_writes_summary(self):
        fake_llm = FakeLLM([LLMResponse(content="用户提问，模型完成回答")])
        thread_store = self.sessions.get_or_create_thread("test:compact")
        for index in range(30):
            thread_store.add("user", f"message-{index}")
            thread_store.append_history([{"role": "user", "content": f"message-{index}"}])

        compact = CompactService(thread_store=thread_store, llm=fake_llm, config=self.config)
        did_compact = await compact.run_if_needed(force=True)

        self.assertTrue(did_compact)
        self.assertEqual(len(thread_store.messages), 20)
        self.assertEqual(thread_store.get_summary_count(), 1)
        self.assertTrue(thread_store.history_path.exists())
        with open(thread_store.history_path, encoding="utf-8") as handle:
            self.assertEqual(sum(1 for _ in handle), 30)

    async def test_build_context_prefers_memory_over_summary(self):
        thread_store = self.sessions.get_or_create_thread("test:context")
        thread_store.add("user", "最近做了什么")
        thread_store.append_summary("这是旧摘要")
        thread_store.memory_path.write_text("这是长期记忆", encoding="utf-8")

        messages = build_context(thread_store=thread_store, workspace=self.root)

        self.assertEqual(messages[0]["content"], "这是长期记忆")

    async def test_build_context_supports_thread_and_messages_without_store(self):
        thread = ThreadRef(id="thread_ctx", title="ctx")
        task_run = TaskRun(id="task_ctx", thread_id=thread.id, objective="看看上下文")

        messages = build_context(
            workspace=self.root,
            thread=thread,
            task_run=task_run,
            messages=[{"role": "user", "content": "看看上下文"}],
        )

        self.assertGreaterEqual(len(messages), 2)
        self.assertEqual(messages[-1], {"role": "user", "content": "看看上下文"})

    async def test_run_task_updates_working_memory(self):
        service = self.create_service(
            stream_responses=[
                [
                    LLMStreamChunk(content="这次结果"),
                    LLMStreamChunk(finish_reason="stop"),
                ]
            ]
        )

        await service.run_task(TaskRequest(thread_id="thread:memory", objective="记录一下"))

        thread_memory_path = service.working_memory_store.get_path("thread:memory")
        self.assertTrue(thread_memory_path.exists())
        payload = json.loads(thread_memory_path.read_text(encoding="utf-8"))
        self.assertEqual(payload["thread_id"], "thread:memory")
        self.assertEqual(payload["objective"], "记录一下")
        self.assertEqual(payload["user_intent"], "记录一下")
        self.assertEqual(payload["summary"], "这次结果")

    async def test_build_context_drops_orphan_tool_history(self):
        thread_store = self.sessions.get_or_create_thread("test:orphan-tool")
        thread_store.add_message({"role": "user", "content": "打开微信"})
        thread_store.add_message({"role": "assistant", "content": ""})
        thread_store.add_message({"role": "tool", "content": "[Exit code: 0]"})
        thread_store.add_message({"role": "assistant", "content": "开了"})

        messages = build_context(thread_store=thread_store, workspace=self.root)
        payload_messages = [message for message in messages if message["role"] != "system"]

        self.assertEqual(
            payload_messages,
            [
                {"role": "user", "content": "打开微信"},
                {"role": "assistant", "content": "开了"},
            ],
        )


if __name__ == "__main__":
    unittest.main()
