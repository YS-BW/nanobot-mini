"""共享运行时契约测试。"""

from datetime import datetime
import unittest

from tests.support import load_repo_module


events_module = load_repo_module("bananabot.runtime.events", "bananabot/runtime/events.py")
models_module = load_repo_module("bananabot.runtime.models", "bananabot/runtime/models.py")

EventEnvelope = events_module.EventEnvelope
Step = models_module.Step
StepKind = models_module.StepKind
StepStatus = models_module.StepStatus
TaskRun = models_module.TaskRun
TaskRunStatus = models_module.TaskRunStatus
ThreadRef = models_module.ThreadRef
Turn = models_module.Turn
TurnStatus = models_module.TurnStatus


class RuntimeContractTests(unittest.TestCase):
    """冻结 Phase 0 共享契约，避免并发重构时各写一套。"""

    def test_task_run_status_values_are_frozen(self):
        self.assertEqual(
            [status.value for status in TaskRunStatus],
            ["pending", "running", "completed", "failed"],
        )

    def test_turn_status_values_are_frozen(self):
        self.assertEqual(
            [status.value for status in TurnStatus],
            ["pending", "running", "completed", "failed"],
        )

    def test_step_status_values_are_frozen(self):
        self.assertEqual(
            [status.value for status in StepStatus],
            ["pending", "running", "completed", "failed"],
        )

    def test_step_kind_values_are_frozen(self):
        self.assertEqual(
            [kind.value for kind in StepKind],
            [
                "reasoning",
                "tool_call_requested",
                "tool_call_started",
                "tool_call_finished",
                "assistant_message",
            ],
        )

    def test_runtime_models_use_stable_prefixes_and_default_states(self):
        thread = ThreadRef(id="thread_demo", title="demo")
        task_run = TaskRun(thread_id=thread.id, objective="完成测试")
        turn = Turn(task_run_id=task_run.id, sequence=1)
        step = Step(task_run_id=task_run.id, turn_id=turn.id, kind=StepKind.REASONING, sequence=1)

        self.assertTrue(task_run.id.startswith("task_"))
        self.assertTrue(turn.id.startswith("turn_"))
        self.assertTrue(step.id.startswith("step_"))
        self.assertEqual(task_run.status, TaskRunStatus.PENDING)
        self.assertEqual(turn.status, TurnStatus.PENDING)
        self.assertEqual(step.status, StepStatus.PENDING)

    def test_event_envelope_keeps_runtime_identity_fields(self):
        timestamp = datetime(2026, 4, 21, 12, 0, 0)
        event = EventEnvelope(
            type="assistant_message",
            status="completed",
            message="完成",
            payload={"text": "完成"},
            thread_id="thread_demo",
            task_run_id="task_demo",
            turn_id="turn_demo",
            step_id="step_demo",
            event_id="evt_demo",
            timestamp=timestamp,
        )

        self.assertEqual(event.payload["text"], "完成")
        self.assertEqual(event.thread_id, "thread_demo")
        self.assertEqual(event.task_run_id, "task_demo")
        self.assertEqual(event.turn_id, "turn_demo")
        self.assertEqual(event.step_id, "step_demo")
        self.assertEqual(event.event_id, "evt_demo")
        self.assertEqual(event.timestamp, timestamp)


if __name__ == "__main__":
    unittest.main()
