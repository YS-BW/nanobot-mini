"""运行时状态仓库测试。"""

from datetime import datetime
import tempfile
import unittest
from pathlib import Path

from tests.support import load_repo_module


events_module = load_repo_module("bananabot.runtime.events", "bananabot/runtime/events.py")
models_module = load_repo_module("bananabot.runtime.models", "bananabot/runtime/models.py")
store_module = load_repo_module("bananabot.infra.runtime_state_store", "bananabot/infra/runtime_state_store.py")

EventEnvelope = events_module.EventEnvelope
FileRuntimeStateStore = store_module.FileRuntimeStateStore
Step = models_module.Step
StepKind = models_module.StepKind
StepStatus = models_module.StepStatus
TaskRun = models_module.TaskRun
TaskRunStatus = models_module.TaskRunStatus
ThreadRef = models_module.ThreadRef
Turn = models_module.Turn
TurnStatus = models_module.TurnStatus


class RuntimeStateStoreTests(unittest.TestCase):
    """验证最小 thread/task/turn/event 持久化骨架。"""

    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        self.store = FileRuntimeStateStore(self.root / "runtime-state")

    def tearDown(self):
        self.tempdir.cleanup()

    def test_store_round_trip_for_runtime_entities(self):
        now = datetime(2026, 4, 21, 12, 30, 0)
        thread = ThreadRef(id="thread_demo", title="demo", metadata={"workspace": "/tmp"}, created_at=now, updated_at=now)
        task_run = TaskRun(
            id="task_demo",
            thread_id=thread.id,
            objective="检查状态",
            status=TaskRunStatus.RUNNING,
            metadata={"source": "test"},
            created_at=now,
            updated_at=now,
        )
        turn = Turn(
            id="turn_demo",
            task_run_id=task_run.id,
            sequence=1,
            status=TurnStatus.RUNNING,
            created_at=now,
            updated_at=now,
        )
        step = Step(
            id="step_demo",
            task_run_id=task_run.id,
            turn_id=turn.id,
            kind=StepKind.TOOL_CALL_FINISHED,
            sequence=2,
            status=StepStatus.COMPLETED,
            payload={"tool": "exec", "exit_code": 0},
            created_at=now,
            updated_at=now,
        )

        self.store.save_thread(thread)
        self.store.save_task_run(task_run)
        self.store.save_turn(turn)
        self.store.save_step(step)

        self.assertEqual(self.store.load_thread(thread.id), thread)
        self.assertEqual(self.store.load_task_run(task_run.id), task_run)
        self.assertEqual(self.store.load_turn(turn.id), turn)
        self.assertEqual(self.store.load_step(step.id), step)

    def test_store_lists_entities_by_runtime_relationship(self):
        now = datetime(2026, 4, 21, 13, 0, 0)
        thread = ThreadRef(id="thread_alpha", created_at=now, updated_at=now)
        task_a = TaskRun(id="task_a", thread_id=thread.id, objective="A", created_at=now, updated_at=now)
        task_b = TaskRun(id="task_b", thread_id=thread.id, objective="B", created_at=now, updated_at=now)
        turn_b2 = Turn(id="turn_b2", task_run_id=task_b.id, sequence=2, created_at=now, updated_at=now)
        turn_b1 = Turn(id="turn_b1", task_run_id=task_b.id, sequence=1, created_at=now, updated_at=now)
        step_b1_2 = Step(
            id="step_b1_2",
            task_run_id=task_b.id,
            turn_id=turn_b1.id,
            kind=StepKind.REASONING,
            sequence=2,
            created_at=now,
            updated_at=now,
        )
        step_b1_1 = Step(
            id="step_b1_1",
            task_run_id=task_b.id,
            turn_id=turn_b1.id,
            kind=StepKind.ASSISTANT_MESSAGE,
            sequence=1,
            created_at=now,
            updated_at=now,
        )

        self.store.save_thread(thread)
        self.store.save_task_run(task_b)
        self.store.save_task_run(task_a)
        self.store.save_turn(turn_b2)
        self.store.save_turn(turn_b1)
        self.store.save_step(step_b1_2)
        self.store.save_step(step_b1_1)

        self.assertEqual([task.id for task in self.store.list_task_runs(thread.id)], ["task_a", "task_b"])
        self.assertEqual([turn.id for turn in self.store.list_turns(task_b.id)], ["turn_b1", "turn_b2"])
        self.assertEqual([step.id for step in self.store.list_steps(turn_b1.id)], ["step_b1_1", "step_b1_2"])

    def test_event_log_filters_and_snapshot_aggregate_thread_state(self):
        now = datetime(2026, 4, 21, 14, 0, 0)
        thread = ThreadRef(id="thread_snapshot", title="snapshot", created_at=now, updated_at=now)
        task_run = TaskRun(id="task_snapshot", thread_id=thread.id, objective="snapshot", created_at=now, updated_at=now)
        turn = Turn(id="turn_snapshot", task_run_id=task_run.id, sequence=1, created_at=now, updated_at=now)
        step = Step(
            id="step_snapshot",
            task_run_id=task_run.id,
            turn_id=turn.id,
            kind=StepKind.ASSISTANT_MESSAGE,
            sequence=1,
            payload={"text": "完成"},
            created_at=now,
            updated_at=now,
        )
        matched = EventEnvelope(
            type="assistant_message",
            status="completed",
            payload={"text": "完成"},
            thread_id=thread.id,
            task_run_id=task_run.id,
            turn_id=turn.id,
            step_id=step.id,
            event_id="evt_match",
            timestamp=now,
        )
        ignored = EventEnvelope(
            type="assistant_message",
            status="completed",
            payload={"text": "忽略"},
            thread_id="thread_other",
            task_run_id="task_other",
            turn_id="turn_other",
            step_id="step_other",
            event_id="evt_other",
            timestamp=now,
        )

        self.store.save_thread(thread)
        self.store.save_task_run(task_run)
        self.store.save_turn(turn)
        self.store.save_step(step)
        self.store.append_event(ignored)
        self.store.append_event(matched)

        events = self.store.load_events(thread_id=thread.id)
        snapshot = self.store.load_runtime_snapshot(thread.id)

        self.assertEqual([event.event_id for event in events], ["evt_match"])
        self.assertEqual(snapshot.thread, thread)
        self.assertEqual([task.id for task in snapshot.task_runs], [task_run.id])
        self.assertEqual([item.id for item in snapshot.turns], [turn.id])
        self.assertEqual([item.id for item in snapshot.steps], [step.id])
        self.assertEqual([event.event_id for event in snapshot.events], ["evt_match"])

    def test_event_log_reads_payload_field(self):
        log_path = self.store.root / "event_log.jsonl"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text(
            '{"type":"assistant_delta","status":"running","payload":{"delta":"你"},"thread_id":"thread_payload","event_id":"evt_payload","timestamp":"2026-04-21T15:00:00"}\n',
            encoding="utf-8",
        )

        events = self.store.load_events(thread_id="thread_payload")

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].payload, {"delta": "你"})


if __name__ == "__main__":
    unittest.main()
