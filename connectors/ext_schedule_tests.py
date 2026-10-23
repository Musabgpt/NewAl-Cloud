"""Scheduled tasks (schedule.py): their times in the phone's local time, a missed time run once, every run in the
task's own thread with the journal of the earlier runs (so none repeats them), a notification for each (none for a
quiet check-in with nothing to say), the task changed from its own thread, a connected service used before the screen
(and its tools offered to the task's thread in lean mode), the phone's screen used by one task at a time and a locked
phone waited for, the /schedule and /duet commands and the schedule_task tool."""
import datetime
import os
import tempfile
import threading
import time
import unittest
from types import SimpleNamespace
from unittest import mock

from . import tools  # noqa: F401 - registers every tool first, as the engine does


def ts(y, mo, d, h, mi=0):
    return datetime.datetime(y, mo, d, h, mi).timestamp()


class FakeService:
    """Threads that end at once with a given answer (or keep running while `hold` is set)."""
    def __init__(self, answer="Done: 3 new messages"):
        self.answer = answer
        self.sessions = {}
        self.sent = []
        self.events = []
        self.hold = threading.Event()
        self.busy_ids = set()                # threads the user is writing in
        self.n = 0

    def create(self, root, model=None, mode=None, worktree=False):
        self.n += 1
        s = SimpleNamespace(id="sched-%d" % self.n, root=root, origin=root, model=model, mode=mode, title="",
                            messages=[], save_meta=lambda: None)
        self.sessions[s.id] = s
        return s

    def get(self, sid):
        if sid not in self.sessions:
            raise KeyError(sid)
        return self.sessions[sid]

    def send(self, sid, text):
        self.sent.append((sid, text))
        self.sessions[sid].messages.append({"role": "assistant", "content": self.answer})
        return {"started": True, "session": sid}

    def busy(self, sid):
        return sid in self.busy_ids or (self.hold.is_set() and sid in self.sessions)

    def projects(self):
        return []

    def broadcast(self, ev):
        self.events.append(ev)


class ScheduleTests(unittest.TestCase):
    def setUp(self):
        from . import schedule, settings
        self.schedule = schedule
        self.dir = tempfile.TemporaryDirectory()
        self.root = self.dir.name
        os.makedirs(self.root + "/private")
        os.makedirs(self.root + "/project")
        self.patches = [mock.patch.object(settings, "HOME", self.root + "/private")]
        self.calls = []
        self.lock_state = {"locked": False, "woke": False}

        def phone(action, **args):
            self.calls.append((action, args))
            if action == "wake":
                return dict(self.lock_state, ok=True)
            return {"ok": True}
        self.patches.append(mock.patch.object(schedule, "_phone_call", side_effect=phone))
        self.connected = []                  # the connected services' tools (Activepieces, Gmail...)
        self.patches.append(mock.patch.object(schedule, "_connected", side_effect=lambda: list(self.connected)))
        for p in self.patches:
            p.start()
        schedule._runs.clear()
        schedule._screen_runs.clear()
        schedule._threads.clear()
        schedule._armed[0] = 0
        self.session = SimpleNamespace(id="parent-1", root=self.root + "/project", origin=self.root + "/project",
                                       model="auto", mode="auto-edit")

    def tearDown(self):
        for p in reversed(self.patches):
            p.stop()
        self.schedule._runs.clear()
        self.dir.cleanup()

    # Runs end with a look at the real clock: the tests' times are years ahead of it, so it finds nothing new due.

    def finish_runs(self):
        for t in threading.enumerate():
            if t.name == "musab-schedule-run":
                t.join(10)

    def notes(self):
        return [a for c, a in self.calls if c == "notify"]

    # ------------------------------------------------------------------ times

    def test_times_in_local_time(self):
        s = self.schedule
        now = ts(2026, 10, 23, 9, 0)                                     # a Friday
        self.assertEqual(s.next_run(s.when_of("daily", at="08:00"), now), ts(2026, 10, 24, 8, 0))
        self.assertEqual(s.next_run(s.when_of("daily", at="٢٠:٣٠"), now), ts(2026, 10, 23, 20, 30))
        weekly = s.when_of("weekly", at="18:00", days="mon,الخميس")
        self.assertEqual(weekly["days"], [0, 3])
        self.assertEqual(s.next_run(weekly, now), ts(2026, 10, 26, 18, 0))
        every = s.when_of("every", every="3h", window="08-22")
        self.assertEqual(s.next_run(every, ts(2026, 10, 23, 12, 0)), ts(2026, 10, 23, 15, 0))
        self.assertEqual(s.next_run(every, ts(2026, 10, 23, 20, 0)), ts(2026, 10, 24, 8, 0))   # not at night
        self.assertEqual(s.next_run(every, ts(2026, 10, 23, 3, 0)), ts(2026, 10, 23, 8, 0))
        once = s.when_of("once", at="15:00", date="tomorrow", now=now)
        self.assertEqual(once["ts"], ts(2026, 10, 24, 15, 0))
        self.assertIsNone(s.next_run(once, once["ts"]))
        self.assertEqual(s.when_of("once", in_minutes=30, now=now)["ts"], round(now + 1800))
        self.assertEqual(s.when_of("once", at="08:00", now=now)["ts"], ts(2026, 10, 24, 8, 0))  # today's is past
        for bad in (lambda: s.when_of("every", every="5m"), lambda: s.when_of("daily", at="25:00"),
                    lambda: s.when_of("once", at="08:00", date="2020-01-01", now=now),
                    lambda: s.when_of("weekly", at="08:00", days="")):
            self.assertRaises(s.ScheduleError, bad)

    # ------------------------------------------------------------------ runs

    def test_due_task_runs_in_its_thread_and_notifies(self):
        s, svc = self.schedule, FakeService()
        t = s.add(self.session, "لخصلي الأخبار", s.when_of("daily", at="08:00"), now=ts(2030, 10, 23, 7, 0))
        self.assertEqual(t["next"], ts(2030, 10, 23, 8, 0))
        s.tick(svc, now=ts(2030, 10, 23, 7, 59))
        self.assertEqual(svc.sent, [])                                   # not yet
        s.tick(svc, now=ts(2030, 10, 23, 8, 0, ))
        self.finish_runs()
        self.assertEqual(len(svc.sent), 1)
        sid, text = svc.sent[0]
        self.assertIn("The task: لخصلي الأخبار", text)
        self.assertIn("Nobody is watching", text)
        self.assertIn("first run", text)
        self.assertEqual(svc.sessions[sid].root, self.root + "/project")
        self.assertEqual((svc.sessions[sid].model, svc.sessions[sid].mode), ("auto", "auto-edit"))
        self.assertTrue(svc.sessions[sid].title.startswith("⏰"))
        self.assertEqual(self.notes()[-1]["text"], "Done: 3 new messages")
        task = s.load()[0]
        self.assertEqual(task["last"]["state"], "done")
        self.assertEqual(task["next"], ts(2030, 10, 24, 8, 0))
        self.assertEqual(task["session"], sid)
        self.assertFalse(s.is_run(sid))                                 # the run ended: the user may chat there
        from . import fleet
        self.assertIn(sid, fleet._load())                              # listed with the background agents
        self.assertIn(("schedule_alarm", {"at": int(ts(2030, 10, 24, 8, 0) * 1000)}), self.calls)

    def test_every_run_continues_the_thread_and_reads_what_was_done(self):
        s, svc = self.schedule, FakeService(answer="Posted: «صباح الخير يا جماعة»")
        t = s.add(self.session, "انشر منشور على فيسبوك", s.when_of("daily", at="09:00"), now=ts(2030, 10, 23, 8, 0))
        s.tick(svc, now=ts(2030, 10, 23, 9, 0))
        self.finish_runs()
        svc.answer = "Posted: «مساء الورد»"
        s.tick(svc, now=ts(2030, 10, 24, 9, 0))
        self.finish_runs()
        (first, _), (second, text) = svc.sent
        self.assertEqual(first, second)                                  # one thread for the task
        self.assertEqual(len(svc.sessions), 1)
        self.assertIn("run 2", text)
        self.assertIn("صباح الخير يا جماعة", text)                       # what the first run posted
        self.assertIn("never post the same", text)
        task = s.load()[0]
        self.assertEqual(task["runs"], 2)
        self.assertEqual([h["answer"] for h in task["history"]], ["Posted: «صباح الخير يا جماعة»",
                                                                  "Posted: «مساء الورد»"])
        self.assertEqual(s.task_of(first)["id"], t["id"])

    def test_a_thread_the_user_writes_in_waits(self):
        s, svc = self.schedule, FakeService()
        s.add(self.session, "check the build", s.when_of("daily", at="09:00"), now=ts(2030, 10, 23, 8, 0))
        s.tick(svc, now=ts(2030, 10, 23, 9, 0))
        self.finish_runs()
        svc.busy_ids.add(svc.sent[0][0])
        s.tick(svc, now=ts(2030, 10, 24, 9, 0))
        self.assertEqual(len(svc.sent), 1)
        self.assertTrue(s.load()[0]["pending"])
        svc.busy_ids.clear()
        s.tick(svc, now=ts(2030, 10, 24, 9, 1))
        self.finish_runs()
        self.assertEqual(len(svc.sent), 2)

    def test_missed_times_run_once(self):
        s, svc = self.schedule, FakeService()
        s.add(self.session, "check the build", s.when_of("every", every="1h"), now=ts(2030, 10, 20, 8, 0))
        s.tick(svc, now=ts(2030, 10, 23, 10, 30))                        # the phone was off for three days
        self.finish_runs()
        s.tick(svc, now=ts(2030, 10, 23, 10, 31))
        self.finish_runs()
        self.assertEqual(len(svc.sent), 1)
        self.assertEqual(s.load()[0]["next"], ts(2030, 10, 23, 11, 30))

    def test_quiet_check_in_with_nothing_new_posts_nothing(self):
        s, svc = self.schedule, FakeService(answer="NOTHING_NEW")
        s.duet(self.session, True)
        names = sorted(t["preset"] for t in s.load())
        self.assertEqual(names, ["brief", "checkin"])
        check = [t for t in s.load() if t["preset"] == "checkin"][0]
        s.run_now(svc, check["id"])
        self.finish_runs()
        self.assertIn("NOTHING_NEW", svc.sent[0][1])
        self.assertEqual(self.notes(), [])
        self.assertEqual([t for t in s.load() if t["preset"] == "checkin"][0]["last"]["state"], "quiet")
        s.duet(self.session, True)                                       # twice: still two tasks
        self.assertEqual(len(s.load()), 2)
        s.duet(self.session, False)
        self.assertEqual(s.load(), [])

    def test_one_task_on_the_screen_at_a_time_and_a_locked_phone_waits(self):
        s, svc = self.schedule, FakeService()
        a = s.add(self.session, "افتح واتساب وابعت لأحمد صباح الخير", s.when_of("daily", at="08:00"),
                  now=ts(2030, 10, 23, 7, 0))
        b = s.add(self.session, "open youtube and play the news", s.when_of("daily", at="08:00"),
                  now=ts(2030, 10, 23, 7, 0))
        self.assertTrue(s._public(a)["phone"] and s._public(b)["phone"])
        self.assertFalse(s._public(s.add(self.session, "لخصلي إشعارات واتساب", s.when_of("daily", at="09:00"),
                                         now=ts(2030, 10, 23, 7, 0)))["phone"])   # reading needs no screen
        self.lock_state["locked"] = True
        s.tick(svc, now=ts(2030, 10, 23, 8, 0))
        s.tick(svc, now=ts(2030, 10, 23, 8, 1))
        self.assertEqual(svc.sent, [])
        self.assertEqual(len([n for n in self.notes() if "unlock" in n["text"]]), 2)   # once for each task
        self.lock_state.update(locked=False, woke=True)
        svc.hold.set()                                                   # the first run keeps working
        s.tick(svc, now=ts(2030, 10, 23, 8, 2))
        self.assertEqual(len(svc.sent), 1)
        s.tick(svc, now=ts(2030, 10, 23, 8, 3))
        self.assertEqual(len(svc.sent), 1)                               # the screen is taken
        svc.hold.clear()
        self.finish_runs()                                               # its end starts the next one
        self.finish_runs()
        self.assertEqual(len(svc.sent), 2)
        self.assertIn(("sleep_screen", {}), self.calls)                  # turned on for the run, off after it

    def test_a_connected_service_comes_before_the_screen(self):
        s, svc = self.schedule, FakeService(answer="Posted on the page: «صباح الخير»")
        t = s.add(self.session, "انشر منشور على فيسبوك", s.when_of("daily", at="09:00"), now=ts(2030, 10, 23, 8, 0))
        self.assertTrue(s._public(t)["phone"])                            # nothing connected: the app, on the screen
        self.connected = ["github_list_repos", "connected_activepieces_facebook_pages_cre_0123456789"]
        p = s._public(t)
        self.assertEqual((p["screen"], p["phone"], p["via"]), ("auto", False, ["facebook"]))
        s.tick(svc, now=ts(2030, 10, 23, 9, 0))
        self.finish_runs()
        self.assertNotIn("wake", [c for c, _ in self.calls])              # the screen is left off, the phone locked
        self.assertIn("does not use the phone's screen", svc.sent[0][1])
        s.change(t["id"], screen="yes")                                  # the user's choice wins
        self.assertTrue(s._public(s.load()[0])["phone"])
        s.change(t["id"], phone=False)
        self.assertEqual(s.load()[0]["screen"], "no")
        self.assertRaises(s.ScheduleError, s.change, t["id"], screen="maybe")

    def test_a_tasks_thread_gets_connected_services_tools_in_lean_mode(self):
        s = self.schedule
        t = s.add(self.session, "انشر منشور على فيسبوك", s.when_of("daily", at="09:00"), now=ts(2030, 10, 23, 8, 0))
        tasks = s.load()
        tasks[0]["session"] = "task-thread"
        s.save(tasks)
        few = ["github_list_repos", "termux_exec", "gmail_send", "connected_activepieces_facebook_pages_cre_0123456789"]
        self.assertEqual(s.task_tools("other-thread", few), [])           # an ordinary thread: lean stays lean
        self.assertEqual(s.task_tools("task-thread", few), ["gmail_send",
                                                            "connected_activepieces_facebook_pages_cre_0123456789"])
        many = ["connected_activepieces_piece%02d_0123456789" % i for i in range(40)] + few
        self.assertEqual(s.task_tools("task-thread", many), ["connected_activepieces_facebook_pages_cre_0123456789"])
        mcp = SimpleNamespace(schemas=lambda: [{"type": "function", "function": {"name": "mcp__ap__x%d" % i,
                                                                                "description": "tool %d" % i}}
                                               for i in range(30)] + [
            {"type": "function", "function": {"name": "mcp__ap__post", "description": "Create a Facebook page post"}}])
        self.assertEqual([d["function"]["name"] for d in s.task_mcp("task-thread", mcp)], ["mcp__ap__post"])
        self.assertEqual(s.task_mcp("other-thread", mcp), [])
        self.assertEqual(t["screen"], "auto")

    def test_lean_agent_in_a_tasks_thread_sees_the_connected_tools(self):
        from . import agent, connectors, phone, session, settings
        with mock.patch.object(settings, "CONFIG", os.path.join(self.root, "private", "config.json")), \
                mock.patch.object(phone, "available", lambda: True), \
                mock.patch.object(connectors, "names", lambda: ["github_list_repos", "gmail_send"]):
            client = SimpleNamespace(spec={}, local=False, on_device=False, context=lambda: 128000)
            plain = agent.Agent(session.Session(self.root + "/project"), client=client)
            own = agent.Agent(session.Session(self.root + "/project"), client=client)
            self.addCleanup(plain.memory.close)
            self.addCleanup(own.memory.close)
            self.schedule._threads.add(own.session.id)
            names = lambda a: [d["function"]["name"] for d in a.schemas()]  # noqa: E731
            self.assertNotIn("gmail_send", names(plain))
            self.assertIn("gmail_send", names(own))
            self.assertIn("github_list_repos", names(plain))

    def test_phone_ext_leaves_scheduled_runs_to_the_scheduler(self):
        from . import phone_ext
        self.schedule._runs["sched-x"] = "t1"
        agent = SimpleNamespace(depth=0, cfg={}, session=SimpleNamespace(id="sched-x"))
        with mock.patch.object(phone_ext, "phone_ready", return_value=True), \
                mock.patch.object(phone_ext, "summary", side_effect=AssertionError("no end-of-turn notification")):
            phone_ext.finished(agent, "ok", 120)

    # ------------------------------------------------------------------ commands and the tool

    def test_schedule_command(self):
        s, svc = self.schedule, FakeService()
        out = s.command(svc, self.session, "schedule", "daily 07:30 summarize my GitHub")
        self.assertIn("every day at 07:30", out["reply"])
        out = s.command(svc, self.session, "schedule", "weekly mon,fri 18:00 run the tests")
        self.assertIn("Mon, Fri at 18:00", out["reply"])
        self.assertIn("every 2h (09:00-17:00)", s.command(svc, self.session, "schedule",
                                                          "every 2h 09-17 check the PRs")["reply"])
        self.assertIn("once", s.command(svc, self.session, "schedule", "in 30m remind me")["reply"])
        listing = s.command(svc, self.session, "schedule", "")["reply"]
        self.assertIn("summarize my GitHub", listing)
        self.assertIn("paused", s.command(svc, self.session, "schedule", "pause t1")["reply"])
        self.assertIn("Removed t2", s.command(svc, self.session, "schedule", "remove t2")["reply"])
        natural = s.command(svc, self.session, "schedule", "كل يوم الساعة 8 الصبح لخصلي الأخبار")
        self.assertIn("schedule_task", natural["prompt"])
        self.assertIn("shortest", s.command(svc, self.session, "schedule", "every 5m x")["reply"])
        self.assertIsNone(s.command(svc, self.session, "agents", ""))

    def test_tool_adds_lists_and_edits(self):
        from . import tools as t
        ctx = SimpleNamespace(session=self.session, agent=SimpleNamespace(depth=0), cancel=threading.Event(),
                              emit=lambda ev: None)
        text, meta = t.call(ctx, "schedule_task", {"action": "add", "prompt": "Check the CI of my repo",
                                                    "kind": "weekly", "at": "09:00", "days": "sun"})
        self.assertIn("Sun at 09:00", text)
        tid = meta["task"]
        text, _ = t.call(ctx, "schedule_task", {"action": "list"})
        self.assertIn("Now:", text)
        self.assertIn(tid, text)
        text, _ = t.call(ctx, "schedule_task", {"action": "edit", "id": tid, "kind": "daily", "at": "10:00"})
        self.assertIn("every day at 10:00", text)
        # in the task's own thread, "make it 9pm" needs no id
        self.schedule.change(tid)
        tasks = self.schedule.load()
        tasks[0]["session"] = "own-thread"
        self.schedule.save(tasks)
        own = SimpleNamespace(session=SimpleNamespace(id="own-thread", root=self.root, model="auto", mode="ask"),
                              agent=SimpleNamespace(depth=0), cancel=threading.Event(), emit=lambda ev: None)
        text, _ = t.call(own, "schedule_task", {"action": "edit", "kind": "daily", "at": "21:00"})
        self.assertIn("every day at 21:00", text)
        text, _ = t.call(own, "schedule_task", {"action": "pause"})
        self.assertIn("paused", text)
        with self.assertRaises(t.ToolError):
            t.call(ctx, "schedule_task", {"action": "add", "prompt": "x", "kind": "every", "every": "1m"})
        with self.assertRaises(t.ToolError):
            t.call(ctx, "schedule_task", {"action": "remove", "id": "t99"})
        self.assertIn("schedule_task", t.default_set())

    def test_routes(self):
        s, svc = self.schedule, FakeService()
        svc.sessions["parent-1"] = self.session
        out = s.route(svc, "POST", "/api/schedules/add", b={"session": "parent-1", "prompt": "news", "kind": "daily",
                                                           "at": "08:00", "quiet": True, "screen": "no"})
        self.assertTrue(out["ok"])
        self.assertTrue(out["task"]["quiet"])
        self.assertEqual(out["task"]["screen"], "no")
        edited = s.route(svc, "POST", "/api/schedules/edit", b={"id": out["task"]["id"], "screen": "yes"})
        self.assertTrue(edited["task"]["phone"])
        got = s.route(svc, "GET", "/api/schedules")
        self.assertEqual([x["prompt"] for x in got["tasks"]], ["news"])
        self.assertIn("error", s.route(svc, "POST", "/api/schedules/add", b={"session": "parent-1", "prompt": "x"}))
        self.assertTrue(s.route(svc, "POST", "/api/schedules/pause", b={"id": out["task"]["id"]})["ok"])
        self.assertFalse(s.load()[0]["enabled"])


if __name__ == "__main__":
    unittest.main()
