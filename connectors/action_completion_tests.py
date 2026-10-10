"""Exercise the real agent and phone adapter against successful-action loops."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from . import agent, continuity, phone, providers, session, settings, task_state


def opened_calls(native):
    return sum(c.args[0] == "open_app" for c in native.call_args_list)


class ActionCompletionTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        base = Path(tmp.name)
        for name in ("HOME", "SESSIONS", "CHECKPOINTS", "CONFIG"):
            p = patch.object(settings, name, str(base / name.lower()))
            p.start()
            self.addCleanup(p.stop)
        p = patch.object(phone, "available", return_value=True)
        p.start()
        self.addCleanup(p.stop)
        self.s = session.Session(str(base), mode="full-auto")
        self.s.tool_names = list(set(self.s.tool_names + ["phone", "task_complete"]))
        self.events, self.requests = [], []

    def make_agent(self, choose):
        def chat(messages, **kwargs):
            self.requests.append(copy.deepcopy(messages))
            out = providers.Completion()
            item = choose(len(self.requests), messages)
            if isinstance(item, str):
                out.content = item
            else:
                out.tool_calls = [{"id": "call-%d-%d" % (len(self.requests), i),
                    "name": name, "arguments": json.dumps(args)}
                    for i, (name, args) in enumerate(item)]
            out.usage = {"prompt": 950, "output": 10, "cached": 900, "new": 50}
            out.finish = "stop"
            return out
        client = SimpleNamespace(id="repeat-success", spec={"provider": "openai"},
            local=False, on_device=False, context=lambda: 1000,
            default_reasoning=lambda: "off", chat=Mock(side_effect=chat))
        a = agent.Agent(self.s, client=client, emit=self.events.append)
        a.cfg.update(verify=False, test_after_edit=False, auto_context=False,
                     sandbox="off", max_steps=6, auto_compact=.8)
        a._prune_outputs = lambda: 0
        self.addCleanup(a.memory.close)
        return a

    def test_successful_open_stops_even_when_provider_only_repeats_tools(self):
        a = self.make_agent(lambda *_: [("phone", {"action": "open_app", "name": "com.whatsapp"})])
        with patch.object(phone, "call", return_value={"ok": True, "text": "opened WhatsApp"}) as native:
            answer = a.run("افتح واتساب")
        self.assertEqual(opened_calls(native), 1)
        self.assertEqual(a.client.chat.call_count, 1)
        self.assertIn("WhatsApp", answer)
        self.assertEqual(self.events[-1]["error"], "")
        self.assertEqual(task_state.resume(self.s.root, self.s.active_task_id)["status"], "complete")

    def test_compaction_keeps_actual_call_and_result_after_request(self):
        a = self.make_agent(lambda n, _: [("phone", {"action": "apps"}),
                                        ("phone", {"action": "open_app", "name": "WhatsApp"})]
                            if n == 1 else "Next step requires selecting the contact.")
        with patch.object(phone, "call", side_effect=lambda action, **_: {"ok": True,
                "text": "opened WhatsApp" if action == "open_app" else "WhatsApp (com.whatsapp)"}):
            a.run("افتح واتساب ثم ابحث عن جهة الاتصال")
        self.assertEqual(self.requests[-1][-1]["role"], "tool")
        self.assertEqual(self.requests[-1][-1]["content"], "opened WhatsApp")
        calls = {c["id"] for m in self.requests[-1] for c in m.get("tool_calls", [])}
        self.assertTrue(all(m["tool_call_id"] in calls for m in self.requests[-1] if m["role"] == "tool"))

    def test_failed_native_result_is_not_success(self):
        a = self.make_agent(lambda n, _: [("phone", {"action": "open_app", "name": "WhatsApp"})]
                            if n == 1 else "تعذر فتح التطبيق.")
        with patch.object(phone, "call", return_value={"ok": False, "text": "permission denied"}):
            a.run("افتح واتساب")
        end = next(e for e in self.events if e["type"] == "tool_end" and e["name"] == "phone")
        self.assertFalse(end["ok"])

    def test_complex_request_does_not_relaunch_completed_action(self):
        a = self.make_agent(lambda *_: [("phone", {"action": "open_app", "name": "WhatsApp"})])
        with patch.object(phone, "call", return_value={"ok": True, "text": "opened WhatsApp"}) as native:
            a.run("افتح واتساب ثم ابحث عن جهة الاتصال")
        self.assertEqual(opened_calls(native), 1)
        self.assertLess(a.client.chat.call_count, 6)
        self.assertEqual(self.events[-1]["error"], "repeated_success_loop")
        self.assertEqual(task_state.resume(self.s.root, self.s.active_task_id)["status"], "active")

    def test_completion_survives_restart_but_explicit_new_request_runs_again(self):
        def looping(*_):
            return [("phone", {"action": "open_app", "name": "WhatsApp"})]
        with patch.object(phone, "call", return_value={"ok": True, "text": "opened WhatsApp"}) as native:
            self.make_agent(looping).run("افتح واتساب")
            self.s.replace_messages(continuity.compact_messages(self.s, ""))
            self.s = session.Session.load(self.s.id)
            resumed = self.make_agent(looping)
            resumed.run("كمل")
            self.assertEqual(opened_calls(native), 1)
            self.assertEqual(resumed.client.chat.call_count, 0)
            self.make_agent(looping).run("افتح واتساب")
            self.assertEqual(opened_calls(native), 2)

    def test_followup_with_more_work_does_not_reuse_terminal_answer(self):
        with patch.object(phone, "call", return_value={"ok": True, "text": "opened WhatsApp"}):
            self.make_agent(lambda *_: [("phone", {"action": "open_app", "name": "WhatsApp"})]).run("افتح واتساب")
            a = self.make_agent(lambda *_: "سأتابع البحث عن جهة الاتصال.")
            a.run("كمل وابحث عن جهة الاتصال")
            self.assertGreater(a.client.chat.call_count, 0)

    def test_remaining_calls_in_same_batch_are_not_executed_after_completion(self):
        a = self.make_agent(lambda *_: [("phone", {"action": "open_app", "name": "WhatsApp"}),
                                       ("phone", {"action": "open_app", "name": "com.whatsapp"})])
        with patch.object(phone, "call", return_value={"ok": True, "text": "opened WhatsApp"}) as native:
            a.run("افتح تطبيق واتساب على الجهاز")
        self.assertEqual(opened_calls(native), 1)
        self.assertTrue(any(e.get("meta", {}).get("skipped") for e in self.events))

    def test_two_app_task_reaches_second_app(self):
        a = self.make_agent(lambda n, _: [("phone", {"action": "open_app", "name": "WhatsApp" if n == 1 else "Chrome"})]
                            if n <= 2 else "تم فتح التطبيقين.")
        with patch.object(phone, "call", side_effect=lambda action, **kw: {"ok": True,
                "text": "opened " + kw.get("name", "")}) as native:
            a.run("افتح واتساب ثم افتح كروم")
        self.assertEqual(opened_calls(native), 2)
        self.assertEqual(a.client.chat.call_count, 3)

    def test_completed_checkpoint_is_not_reopened_by_supervisor(self):
        def script(n, _):
            if n == 1:
                return [("write", {"path": "done.txt", "content": "done"})]
            return [("task_complete", {"task_id": self.s.active_task_id, "summary": "File saved."})]
        a = self.make_agent(script)
        a.run("Create done.txt containing done")
        self.assertEqual(Path(self.s.root, "done.txt").read_text(), "done")
        self.assertEqual(a.client.chat.call_count, 2)
        self.assertEqual(task_state.resume(self.s.root, self.s.active_task_id)["status"], "complete")

    def test_completion_does_not_bypass_failed_project_verification(self):
        def script(n, _):
            if n == 1:
                return [("write", {"path": "done.txt", "content": "bad"})]
            if n == 3:
                return [("edit", {"path": "done.txt", "old": "bad", "new": "good"})]
            return [("task_complete", {"task_id": self.s.active_task_id, "summary": "File verified."})]
        a = self.make_agent(script)
        a._verify = Mock(side_effect=[(False, "Expected good", "check"), (True, "passed", "check")])
        a.run("Create and verify done.txt", verify=True)
        self.assertEqual(a.client.chat.call_count, 4)
        self.assertEqual(a._verify.call_count, 2)
        self.assertEqual(Path(self.s.root, "done.txt").read_text(), "good")
        self.assertEqual(self.events[-1]["error"], "")
        self.assertTrue(self.s.action_state["terminal"])

    def test_denied_phone_permission_never_executes_or_completes(self):
        a = self.make_agent(lambda n, _: [("phone", {"action": "open_app", "name": "WhatsApp"})]
                            if n == 1 else "Permission is required.")
        a._permission = lambda *_: (False, "user denied")
        with patch.object(phone, "call") as native:
            a.run("افتح واتساب")
        self.assertEqual(opened_calls(native), 0)
        self.assertFalse(self.s.action_state["terminal"])


class CompletionContractTests(unittest.TestCase):
    def test_explicit_repeat_count_is_honored_without_unbounded_replays(self):
        from .action_completion import CompletionGuard
        for instruction in ("Run the benchmark twice", "شغل الاختبار مرتين", "Run it 3 times"):
            s = SimpleNamespace(active_task_anchor=instruction, save_meta=Mock(), todo=[], goal="")
            g = CompletionGuard(s, instruction)
            args = {"command": "python benchmark.py"}
            for _ in range(g.state["repeat_limit"]):
                self.assertFalse(g.replay("bash", args, "run"))
                g.observe("bash", args, "run", "benchmark passed", {"exit": 0}, True)
            self.assertTrue(g.replay("bash", args, "run"))

    def test_unverified_completion_is_not_durable_across_crash(self):
        from .action_completion import CompletionGuard
        s = SimpleNamespace(active_task_anchor="Create file", active_task_id="one", save_meta=Mock(), todo=[], goal="")
        g = CompletionGuard(s, s.active_task_anchor)
        g.observe("write", {"path": "a", "content": "x"}, "edit", "wrote a", {}, True)
        g.observe("task_complete", {"summary": "done"}, "meta", "done", {"completed": True, "task_id": "one"}, True)
        self.assertTrue(g.answer())
        self.assertFalse(CompletionGuard(s, "كمل").answer())
        g.finish()
        self.assertEqual(CompletionGuard(s, "كمل").answer(), "done")

    def test_single_action_contract_does_not_claim_complex_or_wrong_target(self):
        from .action_completion import CompletionGuard
        for instruction, tool_target, result in (
            ("افتح واتساب ثم ارسل رسالة", "WhatsApp", "opened WhatsApp"),
            ("افتح واتساب", "Chrome", "opened Chrome"),
            ("افتح واتساب", "WhatsApp", "opened Telegram"),
            ("افتح واتساب", "WhatsApp", "starting WhatsApp"),
            ("كيف افتح واتساب؟", "WhatsApp", "opened WhatsApp"),
            ("لا تفتح واتساب", "WhatsApp", "opened WhatsApp"),
        ):
            s = SimpleNamespace(active_task_anchor=instruction, save_meta=Mock(), todo=[], goal="")
            guard = CompletionGuard(s, instruction)
            guard.observe("phone", {"action": "open_app", "name": tool_target}, "phone", result,
                          {"phone": {"ok": True}}, True)
            self.assertFalse(guard.answer(), instruction)

    def test_pending_and_failed_results_never_complete_or_become_receipts(self):
        from .action_completion import CompletionGuard
        for meta in ({"phone": {"ok": False}}, {"phone": {"ok": True}, "pending": True},
                     {"phone": {"ok": True}, "status": "running"}, {"phone": {}},
                     {"phone": {"ok": True}, "exit_code": 1}):
            s = SimpleNamespace(active_task_anchor="افتح واتساب", save_meta=Mock(), todo=[], goal="")
            guard = CompletionGuard(s, "افتح واتساب")
            args = {"action": "open_app", "name": "WhatsApp"}
            guard.observe("phone", args, "phone", "opened WhatsApp", meta, True)
            self.assertFalse(guard.answer())
            self.assertFalse(guard.replay("phone", args, "phone"))

    def test_phone_inspections_do_not_reset_compaction_epoch(self):
        from .progress_guard import Guard
        s = SimpleNamespace(read_attempts={}, compact_since_tool=1, save_meta=Mock())
        g = Guard(s)
        for action in ("screen", "apps", "battery", "device", "screenshot"):
            g.after("phone", {"action": action}, "phone", "unchanged screen")
        self.assertEqual(s.compact_since_tool, 1)

    def test_intervening_action_allows_valid_reopen_and_gestures_not_cached(self):
        from .action_completion import CompletionGuard
        s = SimpleNamespace(active_task_anchor="Work in two apps", save_meta=Mock(), todo=[], goal="")
        g = CompletionGuard(s, s.active_task_anchor)
        args = {"action": "open_app", "name": "WhatsApp"}
        g.observe("phone", args, "phone", "opened WhatsApp", {"phone": {"ok": True}}, True)
        self.assertTrue(g.replay("phone", args, "phone"))
        g.observe("phone", {"action": "key", "name": "home"}, "phone", "pressed home", {"phone": {"ok": True}}, True)
        self.assertFalse(g.replay("phone", args, "phone"))
        g.observe("phone", {"action": "tap", "item": 1}, "phone", "tapped", {"phone": {"ok": True}}, True)
        self.assertFalse(g.replay("phone", {"action": "tap", "item": 1}, "phone"))


if __name__ == "__main__":
    unittest.main()
