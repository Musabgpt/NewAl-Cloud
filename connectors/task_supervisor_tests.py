import os
from pathlib import Path
import tempfile
import threading
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from . import task_state, task_supervisor


class TaskSupervisorTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "project"
        self.root.mkdir()
        self.store = Path(self.tmp.name) / "tasks"
        self.env = patch.dict(os.environ, {
            "NEWAL_TASK_STATE_HOME": str(self.store),
            "NEWAL_SUPERVISOR_HEARTBEAT_SECONDS": "0.05",
            "NEWAL_SUPERVISOR_STALL_SECONDS": "0.10",
            "NEWAL_SUPERVISOR_HARD_TIMEOUT_SECONDS": "0.40",
            "NEWAL_SUPERVISOR_MAX_RECOVERIES": "2",
        }, clear=False)
        self.env.start()
        self.addCleanup(self.env.stop)
        self.session = SimpleNamespace(id="session-test", root=str(self.root))
        self.user_cancel = threading.Event()
        self.events = []

    def make(self, objective="Build and test the project", turn=1):
        return task_supervisor.TaskSupervisor(
            self.session, self.user_cancel, self.events.append, objective, turn
        )

    def wait_for(self, predicate, timeout=1.5):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if predicate():
                return True
            time.sleep(0.01)
        return bool(predicate())

    def test_manual_stop_sets_real_cancel_and_preserves_resume_checkpoint(self):
        sup = self.make()
        sup.start()
        sup.request_stop()
        self.assertTrue(sup.cancel_token.is_set())
        self.assertEqual(sup.cancel_token.reason(), "user")
        row = task_state.resume(self.root, sup.task_id)
        self.assertEqual(row["status"], "active")
        self.assertIn("Stopped by user", row["checkpoint"]["blocker"])
        sup.finish(error="interrupted")
        self.assertEqual(task_state.resume(self.root, sup.task_id)["status"], "active")

    def test_watchdog_emits_heartbeat_then_cancels_stalled_operation(self):
        sup = self.make()
        sup.start()
        self.assertTrue(self.wait_for(lambda: any(e.get("type") == "task_heartbeat" for e in self.events)))
        self.assertTrue(self.wait_for(lambda: sup.cancel_token.reason() == "watchdog_stall"))
        self.assertEqual(sup.recoveries, 1)
        self.assertTrue(any("another route" in (e.get("text") or "") for e in self.events))
        row = task_state.resume(self.root, sup.task_id)
        self.assertIn("No progress", row["checkpoint"]["blocker"])
        self.assertTrue(sup.consume_watchdog())
        self.assertFalse(sup.cancel_token.is_set())
        sup.finish(error="test cleanup")

    def test_hard_timeout_stops_after_repeated_stalls(self):
        with patch.dict(os.environ, {
            "NEWAL_SUPERVISOR_HEARTBEAT_SECONDS": "0.05",
            "NEWAL_SUPERVISOR_STALL_SECONDS": "0.10",
            "NEWAL_SUPERVISOR_HARD_TIMEOUT_SECONDS": "0.50",
            "NEWAL_SUPERVISOR_MAX_RECOVERIES": "1",
        }, clear=False):
            sup = self.make()
            sup.start()
            self.assertTrue(self.wait_for(lambda: sup.cancel_token.reason() == "watchdog_stall"))
            self.assertTrue(sup.consume_watchdog())
            self.assertTrue(self.wait_for(lambda: sup.cancel_token.reason() == "hard_timeout"))
            snap = sup.snapshot()
            self.assertEqual(snap["reason"], "hard_timeout")
            self.assertGreaterEqual(snap["recoveries"], 1)
            sup.finish(error="timeout")
            row = task_state.resume(self.root, sup.task_id)
            self.assertEqual(row["status"], "active")

    def test_progress_resets_watchdog_and_checkpoints_verified_step(self):
        sup = self.make()
        sup.start()
        time.sleep(0.06)
        sup.observe({"type": "tool_start", "name": "bash", "step": 3})
        time.sleep(0.06)
        self.assertFalse(sup.cancel_token.is_set())
        sup.observe({"type": "verify", "ok": True, "command": "pytest", "step": 4})
        row = task_state.resume(self.root, sup.task_id)
        self.assertIn("Verification passed", row["checkpoint"]["progress"])
        self.assertEqual(row["checkpoint"]["evidence"], "pytest")
        sup.finish(answer="done")
        self.assertEqual(task_state.resume(self.root, sup.task_id)["status"], "complete")

    def test_continuation_reuses_existing_task_state_instead_of_new_memory(self):
        previous = task_state.checkpoint(
            self.root,
            objective="Finish release",
            progress="Tests passed",
            next_step="Build APK",
            evidence="run-123",
        )
        sup = self.make("Continue the release")
        context = sup.resume_context("كمل من حيث توقفنا")
        self.assertIn(previous["id"], context)
        self.assertIn("Build APK", context)
        self.assertIn("Tests passed", context)
        self.assertEqual(sup.previous["id"], previous["id"])

    def test_multi_step_request_gets_bounded_planning_instruction(self):
        sup = self.make()
        text = "Implement this project migration in several phases and verify the build"
        context = sup.planning_context(text)
        self.assertIn("multi-step", context)
        self.assertIn("checklist", context)
        self.assertEqual(sup.planning_context("What is 2+2?"), "")


if __name__ == "__main__":
    unittest.main()
