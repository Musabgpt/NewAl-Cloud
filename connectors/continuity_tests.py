"""Regression tests for repeated context compaction."""
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import Mock
from . import continuity


class TaskContinuityTests(unittest.TestCase):
    def test_preserves_original_and_latest_user(self):
        s = SimpleNamespace(
            messages=[
                {"role": "user", "content": "<context>Musab new</context>\nلعبة طيارة ودبابة بالـ HTML"},
                {"role": "tool", "content": "created index.html, missing game.js", "tool_call_id": "1"},
                {"role": "user", "content": "شغل اللعبة"},
            ], active_objective="شغل اللعبة", goal="", todo=[])
        first = s.messages[0]
        for _ in range(4):
            s.messages = continuity.compact_messages(s, "(no summary)")
            self.assertEqual([m["role"] for m in s.messages], ["user", "assistant", "user"])
            self.assertEqual(s.messages[0], first)
            self.assertEqual(s.messages[-1]["content"], "شغل اللعبة")
            self.assertIn("Active request: شغل اللعبة", s.messages[1]["content"])
            self.assertNotIn("Understood. I'll continue from here.", str(s.messages))

    def test_legacy_fake_user_messages_not_trusted(self):
        s = SimpleNamespace(messages=[
            {"role": "user", "content": "<context>x</context>\nSummary of the conversation so far:\n(none)"},
            {"role": "user", "content": "Conversation compacted: (no summary)"},
        ], active_objective="شغل اللعبة", goal="", todo=[])
        out = continuity.compact_messages(s, "")
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["role"], "assistant")
        self.assertIn("شغل اللعبة", out[0]["content"])

    def test_lost_task_is_detected_once(self):
        self.assertTrue(continuity.lost_task_reply("I don't have a task.", "make a game"))
        self.assertTrue(continuity.lost_task_reply("ما عندي مهمة، شو بدك أعمل؟", "شغل اللعبة"))
        self.assertFalse(continuity.lost_task_reply("I don't have a task.", ""))
        self.assertFalse(continuity.lost_task_reply("Game needs game.js.", "make a game"))

    def test_repeated_compaction_without_tool_progress_stops_instead_of_looping(self):
        from .agent import Agent
        from . import providers
        s = SimpleNamespace(
            messages=[{"role":"user","content":"Build HTML plane and tank game"},
                      {"role":"assistant","content":"Started work"},
                      {"role":"assistant","content":"Still inspecting"},
                      {"role":"user","content":"Continue testing"}],
            goal="", todo=[{"content":"Run browser tests","status":"pending"}],
            active_objective="Continue testing", last_prompt_tokens=980,
            compact_since_tool=0, id="test")
        s.replace_messages = lambda msgs, note="": setattr(s, "messages", msgs)
        s.save_meta = Mock()
        a = Agent.__new__(Agent)
        a.session = s
        a.cfg = {"auto_compact": .8}
        a.client = SimpleNamespace(context=lambda: 1000,
                                   chat=Mock(return_value=SimpleNamespace(content="Summary")))
        a.request_messages = lambda: list(s.messages)
        a.cancel = threading.Event()
        a.emit = Mock()
        a._prune_outputs = lambda: 0
        for turn in range(2):
            self.assertTrue(a._maybe_compact())
            self.assertEqual(s.compact_since_tool, turn + 1)
            s.messages.append({"role":"assistant","content":"Waiting without tool progress"})
            s.last_prompt_tokens = 950
        with self.assertRaises(providers.ProviderError):
            a._maybe_compact()
        self.assertEqual(a.client.chat.call_count, 2,
                         "No third summary request may be sent without tool progress")

    def test_patched_agent_compaction(self):
        from .agent import Agent
        s = SimpleNamespace(
            messages=[{"role":"user","content":"اعمل لعبة HTML"},
                      {"role":"assistant","content":"بدأت بناء الملفات"},
                      {"role":"tool","content":"index.html exists; game.js missing"},
                      {"role":"user","content":"شغل اللعبة"}],
            goal="", todo=[], active_objective="شغل اللعبة", last_prompt_tokens=980, id="test")
        s.replace_messages = lambda msgs, note="": setattr(s, "messages", msgs)
        s.save_meta = Mock()
        s.compact_since_tool = 0
        agent = Agent.__new__(Agent)
        agent.session = s
        agent.cfg = {"auto_compact": .8}
        agent.client = SimpleNamespace(context=lambda: 1000,
                                       chat=Mock(return_value=SimpleNamespace(content="(no summary)")))
        agent.request_messages = lambda: list(s.messages)
        agent.cancel = threading.Event()
        agent.emit = Mock()
        self.assertTrue(agent._maybe_compact(force=True))
        self.assertEqual([m["role"] for m in s.messages], ["user", "assistant", "user"])
        self.assertIsNone(agent.client.chat.call_args.kwargs["tools"])


if __name__ == "__main__":
    unittest.main()
