"""Regression: same workspace can host HTML-game and WhatsApp tasks safely."""
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

from . import continuity, task_identity, task_state, task_supervisor


class TaskIdentityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.session = SimpleNamespace(id="same-chat", root=str(self.root),
                                       active_objective="", active_task_anchor="",
                                       active_task_id="", todo=[], goal="", goal_progress=0,
                                       save_meta=Mock())

    def test_switch_game_to_whatsapp_resets_stale_checklist(self):
        s = self.session
        task_identity.activate(s, "اعمل لعبة طيارة ودبابة HTML")
        s.todo = [{"text": "Test game in browser", "status": "pending"}]
        s.goal = "Verify game"
        s.read_attempts = {"previous-game-inspection": 2}
        s.consecutive_inspections = 9
        s.compact_since_tool = 2
        task_identity.activate(s, "افتح واتساب")
        self.assertEqual(s.active_objective, "افتح واتساب")
        self.assertEqual(s.active_task_anchor, "افتح واتساب")
        self.assertEqual(s.todo, [])
        self.assertEqual(s.goal, "")
        self.assertEqual(s.read_attempts, {})
        self.assertEqual(s.consecutive_inspections, 0)
        self.assertEqual(s.compact_since_tool, 0)

    def test_game_followup_does_not_start_new_task(self):
        s = self.session
        task_identity.activate(s, "اعمل لعبة طيارة ودبابة HTML")
        s.active_task_id = "game-task"
        s.todo = [{"text": "Open game", "status": "pending"}]
        task_identity.activate(s, "شغل اللعبة")
        self.assertEqual(s.active_task_id, "game-task")
        self.assertEqual(s.active_task_anchor, "اعمل لعبة طيارة ودبابة HTML")
        self.assertEqual(len(s.todo), 1)

    def test_continue_whatsapp_does_not_resume_old_game(self):
        s = self.session
        game = task_state.checkpoint(s.root, objective="اعمل لعبة HTML",
                   progress="Written game.html", next_step="Open Chrome",
                   session_id=s.id)
        task_identity.activate(s, "اعمل لعبة HTML")
        s.active_task_id = game["id"]
        task_identity.activate(s, "افتح واتساب")
        task_identity.activate(s, "كمل")
        self.assertEqual(s.active_objective, "افتح واتساب")
        self.assertIsNone(task_identity.previous_checkpoint(s, True))
        sup = task_supervisor.TaskSupervisor(s, threading.Event(), None, "كمل", 3)
        self.assertEqual(sup.objective, "افتح واتساب")
        self.assertNotEqual(sup.task_id, game["id"])
        self.assertFalse(sup.resume_context("كمل"))

    def test_pinned_whatsapp_continuation_ignores_last_project_task(self):
        s = self.session
        game = task_state.checkpoint(s.root, objective="اعمل لعبة HTML",
                                     session_id=s.id)
        task_identity.activate(s, "افتح واتساب")
        wa = task_state.checkpoint(s.root, objective="افتح واتساب",
                                   progress="WhatsApp permission pending",
                                   next_step="Request Android phone permission",
                                   session_id=s.id)
        s.active_task_id = wa["id"]
        # Old task can be 'last updated' but must not supersede the pin.
        task_state.checkpoint(s.root, task_id=game["id"], blocker="old game",
                              session_id=s.id)
        sup = task_supervisor.TaskSupervisor(s, threading.Event(), None, "كمل", 4)
        self.assertEqual(sup.task_id, wa["id"])
        self.assertIn("permission", sup.resume_context("كمل"))

    def test_default_resume_returns_only_current_task(self):
        s = self.session
        task_state.checkpoint(s.root, objective="game.html", session_id=s.id)
        task_identity.activate(s, "افتح واتساب")
        self.assertIsNone(task_identity.previous_checkpoint(s, True))

    def test_task_list_scopes_to_conversation_not_other_chat(self):
        s = self.session
        task_state.checkpoint(s.root, objective="Game", session_id=s.id)
        task_state.checkpoint(s.root, objective="Other chat", session_id="other-chat")
        rows = task_state.list_tasks(s.root, session_id=s.id)
        self.assertEqual([r["objective"] for r in rows], ["Game"])

    def test_task_compaction_drops_old_game_messages_and_evidence(self):
        s = self.session
        s.messages = [
            {"role": "user", "content": "<context>workspace</context>\nاعمل لعبة HTML"},
            {"role": "tool", "content": "game.html 334 lines", "tool_call_id": "g"},
            {"role": "assistant", "content": "Conversation compacted: game ready"},
            {"role": "user", "content": "افتح واتساب"},
            {"role": "user", "content": "كمل"},
        ]
        task_identity.activate(s, "افتح واتساب")
        task_identity.activate(s, "كمل")
        result = continuity.compact_messages(s, "HTML game runs well")
        content = "\n".join(str(x["content"]) for x in result)
        self.assertIn("افتح واتساب", content)
        self.assertIn("كمل", content)
        self.assertNotIn("game.html", content)
        self.assertNotIn("HTML game runs well", content)
        self.assertEqual([x["role"] for x in result], ["user", "assistant", "user"])

    def test_task_anchor_persists_through_repeated_compaction(self):
        s = self.session
        task_identity.activate(s, "افتح واتساب")
        s.messages = [{"role": "user", "content": "اعمل لعبة HTML"},
                      {"role": "user", "content": "افتح واتساب"}]
        for _ in range(4):
            s.messages = continuity.compact_messages(s, "another task")
            blob = " ".join(str(m["content"]) for m in s.messages)
            self.assertNotIn("لعبة HTML", blob)
            self.assertIn("افتح واتساب", blob)


if __name__ == "__main__":
    unittest.main()
