import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from . import task_state


class TaskStateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root_a = Path(self.tmp.name) / "a"
        self.root_b = Path(self.tmp.name) / "b"
        self.root_a.mkdir()
        self.root_b.mkdir()
        self.store = Path(self.tmp.name) / "task-state"
        self.env = patch.dict(os.environ, {"NEWAL_TASK_STATE_HOME": str(self.store)}, clear=False)
        self.env.start()
        self.addCleanup(self.env.stop)

    def test_checkpoint_survives_reload_and_resumes_latest(self):
        row = task_state.checkpoint(
            self.root_a,
            objective="Build the APK",
            progress="Tests passed",
            next_step="Run Gradle",
            evidence="Action 269",
        )
        loaded = json.loads(task_state._path(self.root_a).read_text(encoding="utf-8"))
        self.assertIn(row["id"], loaded["tasks"])
        resumed = task_state.resume(self.root_a)
        self.assertEqual(resumed["id"], row["id"])
        self.assertEqual(resumed["checkpoint"]["next_step"], "Run Gradle")
        self.assertEqual(resumed["checkpoint"]["evidence"], "Action 269")

    def test_projects_are_isolated(self):
        a = task_state.checkpoint(self.root_a, objective="Project A", next_step="A")
        task_state.checkpoint(self.root_b, objective="Project B", next_step="B")
        self.assertEqual(task_state.resume(self.root_a)["id"], a["id"])
        self.assertEqual(task_state.resume(self.root_a)["objective"], "Project A")
        self.assertEqual(task_state.list_tasks(self.root_b)[0]["objective"], "Project B")

    def test_complete_is_not_returned_as_latest_active(self):
        first = task_state.checkpoint(self.root_a, objective="First")
        second = task_state.checkpoint(self.root_a, objective="Second")
        task_state.complete(self.root_a, second["id"], "verified")
        self.assertEqual(task_state.resume(self.root_a)["id"], first["id"])
        self.assertEqual(task_state.resume(self.root_a, second["id"])["status"], "complete")
        self.assertEqual(len(task_state.list_tasks(self.root_a)), 1)
        self.assertEqual(len(task_state.list_tasks(self.root_a, include_completed=True)), 2)

    def test_history_and_fields_are_bounded(self):
        row = task_state.checkpoint(self.root_a, objective="Bounded")
        for i in range(task_state.MAX_HISTORY + 8):
            row = task_state.checkpoint(
                self.root_a,
                task_id=row["id"],
                progress=("x" * (task_state.MAX_FIELD + 100)) + str(i),
                evidence="e" * (task_state.MAX_EVIDENCE + 100),
            )
        self.assertLessEqual(len(row["history"]), task_state.MAX_HISTORY)
        self.assertLessEqual(len(row["checkpoint"]["progress"]), task_state.MAX_FIELD)
        self.assertLessEqual(len(row["checkpoint"]["evidence"]), task_state.MAX_EVIDENCE)

    def test_explicit_continuation_auto_loads_latest_checkpoint_only(self):
        row = task_state.checkpoint(
            self.root_a,
            objective="Finish Android build",
            progress="Tests passed",
            next_step="Build APK",
            evidence="Action 273",
        )
        self.assertEqual(task_state.continuation_context(self.root_a, "ordinary new request"), "")
        context = task_state.continuation_context(self.root_a, "كمل")
        self.assertIn(row["id"], context)
        self.assertIn("Build APK", context)
        self.assertIn("Action 273", context)

    def test_project_verification_updates_active_checkpoint_without_creating_one(self):
        self.assertIsNone(task_state.note_verification(self.root_a, True, "project_tests:passed exit=0"))
        row = task_state.checkpoint(
            self.root_a,
            objective="Repair project",
            progress="Patch applied",
            next_step="Run project tests",
            blocker="waiting for check",
        )
        synced = task_state.note_verification(self.root_a, True, "project_tests:passed exit=0")
        self.assertEqual(synced["id"], row["id"])
        self.assertEqual(synced["checkpoint"]["blocker"], "")
        self.assertEqual(synced["checkpoint"]["evidence"], "project_tests:passed exit=0")

    def test_failed_project_verification_sets_actionable_blocker(self):
        row = task_state.checkpoint(self.root_a, objective="Repair project")
        synced = task_state.note_verification(self.root_a, False, "project_tests:failed exit=1")
        self.assertEqual(synced["id"], row["id"])
        self.assertIn("Verification failed", synced["checkpoint"]["blocker"])
        self.assertIn("rerun", synced["checkpoint"]["next_step"])

    def test_invalid_task_id_is_rejected(self):
        with self.assertRaises(Exception):
            task_state.checkpoint(self.root_a, task_id="../escape", objective="bad")


if __name__ == "__main__":
    unittest.main()
