"""Regression tests reproducing the user's looping Android HTML-game task."""
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from . import progress_guard, task_supervisor


def make_session():
    return SimpleNamespace(
        read_attempts={}, compact_since_tool=2, active_objective="Build HTML game and open it in browser",
        root="/tmp", id="test", tool_names=["read", "task_resume"], save_meta=Mock(),
    )


class ProgressGuardTests(unittest.TestCase):
    def test_same_read_three_times_stops_without_running_again(self):
        from .agent import Agent
        from . import tools
        session = make_session()
        agent = Agent.__new__(Agent)
        agent.session = session
        agent.progress_guard = progress_guard.Guard(session)
        agent.breaker = Mock()
        agent.breaker.record.return_value = ""
        agent.emit = Mock()
        agent._permission = lambda *args: (True, "")
        agent.last_change_step = -1
        agent.step = 1
        agent.cfg = {"hooks": {}}
        call = {"name": "read", "id": "read-1", "arguments": "{}"}
        with patch.object(tools, "call", return_value="game.html is 334 lines") as execution:
            first = agent._one_tool(None, call, {"path": "game.html"})
            second = agent._one_tool(None, call, {"path": "game.html"})
            third = agent._one_tool(None, call, {"path": "game.html"})
        self.assertIn("334 lines", first)
        self.assertIn("already", second)
        self.assertIn("no-progress loop", third)
        self.assertEqual(execution.call_count, 2)
        self.assertEqual(session.compact_since_tool, 2,
                         "read-only calls must not reset the compaction guard")
        self.assertTrue(agent.progress_guard.halted)

    def test_task_resume_counts_as_observation_not_completed_task(self):
        session = make_session()
        g = progress_guard.Guard(session)
        for _ in range(2):
            self.assertEqual(g.before("task_resume", {}, "read"), "")
            self.assertFalse(progress_guard.meaningful(
                "task_resume", "read", "Loaded old game checkpoint"))
        self.assertIn("no-progress loop", g.before("task_resume", {}, "read"))

    def test_repeat_counts_survive_session_restart_and_compaction(self):
        s = make_session()
        first = progress_guard.Guard(s)
        first.before("read", {"path": "game.html"}, "read")
        second = progress_guard.Guard(s)
        second.before("read", {"path": "game.html"}, "read")
        third = progress_guard.Guard(s)
        self.assertIn("no-progress loop", third.before("read", {"path": "game.html"}, "read"))
        self.assertEqual(len(s.read_attempts), 1)
        self.assertNotIn("game.html", str(s.read_attempts),
                         "Persist hashes, not user file paths or tool arguments")

    def test_successful_edit_resets_epoch_and_duplicate_reads(self):
        s = make_session()
        g = progress_guard.Guard(s)
        g.before("read", {"path": "game.html"}, "read")
        g.before("read", {"path": "game.html"}, "read")
        result = g.after("write", {"path": "game.js"}, "edit", "Wrote game.js")
        self.assertEqual(result, "Wrote game.js")
        self.assertEqual(s.compact_since_tool, 0)
        self.assertEqual(s.read_attempts, {})
        self.assertEqual(g.before("read", {"path": "game.html"}, "read"), "")

    def test_unchanged_edit_does_not_fake_progress(self):
        s = make_session()
        g = progress_guard.Guard(s)
        g.after("write", {}, "edit", "game.html already has exactly this content: nothing changed")
        self.assertEqual(s.compact_since_tool, 2)
        self.assertFalse(progress_guard.meaningful("write", "edit", "error: permission denied"))

    def test_continuation_keeps_goal_while_new_task_resets_it(self):
        self.assertTrue(progress_guard.is_continuation("كمل"))
        self.assertTrue(progress_guard.is_continuation("Continue testing"))
        self.assertFalse(progress_guard.is_continuation("Build another game"))
        self.assertTrue(progress_guard.is_observation(
            "runtime_exec", {"command": "ls -l game.html"}, "run"))
        self.assertFalse(progress_guard.is_observation(
            "runtime_exec", {"command": "python -m http.server 8123"}, "run"))

    def test_supervisor_does_not_overwrite_checkpoint_with_read(self):
        sup = task_supervisor.TaskSupervisor.__new__(task_supervisor.TaskSupervisor)
        sup._lock = threading.RLock()
        sup.last_progress_at = 0
        sup.last_event = "previous"
        sup.last_tool = ""
        sup.step = 2
        sup.recoveries = 2
        sup._checkpoint = Mock()
        sup.observe({"type": "tool_end", "name": "task_resume", "ok": True, "step": 3, "meta": {}})
        sup.observe({"type": "tool_end", "name": "read", "ok": True, "step": 4, "meta": {}})
        sup._checkpoint.assert_not_called()
        self.assertEqual(sup.recoveries, 2)

    def test_guard_does_not_count_tool_outputs_as_permission(self):
        g = progress_guard.Guard(make_session())
        self.assertFalse(progress_guard.meaningful("phone", "run", "not allowed: user declined"))
        self.assertFalse(progress_guard.meaningful("write", "edit", "error: cannot write"))
        self.assertEqual(g.before("read", {"path": "existing.html"}, "read"), "")


class ShellInspectionLoopTests(unittest.TestCase):
    def test_cd_prefixed_and_piped_probes_are_inspections(self):
        workspace = "/data/app/files/home/.newal-code/workspaces/Musab new"
        self.assertTrue(progress_guard.is_observation(
            "bash", {"command": 'cd "%s" && find . -maxdepth 2 -type f 2>&1 | head -50' % workspace}, "run"))
        self.assertTrue(progress_guard.is_observation("bash", {"command": "cd x && ls -la"}, "run"))

    def test_writes_and_destructive_probes_are_not_inspections(self):
        for command in ("cat game.html > out.txt", "cd x && python3 app.py",
                        "find . -name '*.tmp' -delete", "find . -exec rm {} \\;",
                        "ls $(rm -rf x)", "ls <<EOF"):
            self.assertFalse(progress_guard.is_observation("bash", {"command": command}, "run"), command)

    def test_many_different_probes_without_action_hit_the_run_limit(self):
        guard = progress_guard.Guard(make_session())
        for i in range(progress_guard.CONSECUTIVE_INSPECTION_LIMIT):
            command = {"command": "ls part%d" % i}
            self.assertEqual(guard.before("bash", command, "run"), "")
            guard.after("bash", command, "run", "part%d.txt" % i)
        self.assertIn("no-progress loop", guard.before("bash", {"command": "find . -name x"}, "run"))

    def test_inspections_interleaved_with_actions_are_not_a_loop(self):
        guard = progress_guard.Guard(make_session())
        for i in range(3 * progress_guard.CONSECUTIVE_INSPECTION_LIMIT):
            self.assertEqual(guard.before("read", {"path": "page%d.html" % i}, "read"), "")
            guard.after("read", {"path": "page%d.html" % i}, "read", "ok")
            self.assertEqual(guard.before("phone", {"action": "tap"}, "run"), "")
            guard.after("phone", {"action": "tap"}, "run", "Tapped the button")

    def test_failed_actions_do_not_end_an_inspection_run(self):
        guard = progress_guard.Guard(make_session())
        for i in range(progress_guard.CONSECUTIVE_INSPECTION_LIMIT):
            guard.before("read", {"path": "a%d" % i}, "read")
            guard.after("read", {"path": "a%d" % i}, "read", "ok")
            guard.after("phone", {"action": "open"}, "run", "not allowed: user declined")
        self.assertIn("no-progress loop", guard.before("read", {"path": "last"}, "read"))

    def test_near_limit_warning_asks_for_a_different_action(self):
        guard = progress_guard.Guard(make_session())
        last = ""
        for i in range(progress_guard.CONSECUTIVE_INSPECTION_LIMIT - 2):
            guard.before("read", {"path": "f%d" % i}, "read")
            last = guard.after("read", {"path": "f%d" % i}, "read", "ok")
        self.assertIn("Stop inspecting", last)


if __name__ == "__main__":
    unittest.main()
