"""The phone does more per call (hands.py): send and search in one call, a tap that scrolls to its text; Arabic matching
with digits and the article (phone_fast, TextFold); and the coding test's stability over k tries (stability.py)."""
import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from types import SimpleNamespace
from unittest import mock

from . import tools  # noqa: F401 - registers every tool first, as the engine does

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
JAVA = os.path.join(ROOT, "android-lite", "app", "src", "main", "java", "dev", "newal", "code", "lite")
NAMES = ["Name %02d" % i for i in range(1, 25)] + ["زيد الخطيب"] + ["Name %02d" % i for i in range(26, 31)]


class FakeApp:
    """The app's phone server on four screens: a WhatsApp chat, YouTube's home and search pages, a notes page with two
    fields, and a contact list that scrolls (8 names shown, 30 in all). A tap by text matches as the app does."""

    def __init__(self, page="chat"):
        self.page = page
        self.field, self.focused, self.sent = "", False, []
        self.buttons = None                     # the chat's buttons after its field (default: Send once typed)
        self.query, self.searched, self.enter_works = "", [], True
        self.top, self.tapped, self.calls = 0, [], []

    def elements(self):
        """[(label, tags, what)] in screen order."""
        if self.page == "chat":
            out = [("Ahmad", "tap", "contact")] + [(m, "", "bubble") for m in self.sent]
            out.append((self.field or "hint: Message", "text field, field, tap" + (", focused" if self.focused else ""),
                        "field"))
            buttons = self.buttons if self.buttons is not None else (["Send"] if self.field else ["Voice message"])
            return out + [(b, "button, tap", b) for b in buttons]
        if self.page == "yt_home":
            return [("Home", "tap", "home"), ("Search", "button, tap", "open_search"), ("Shorts", "tap", "shorts")]
        if self.page == "yt_search":
            return [(self.query or "hint: Search YouTube", "text field, field, tap, focused", "query"),
                    ("Search", "button, tap", "go")]
        if self.page == "yt_results":
            return [(self.query, "text field, field, tap", "query"), ("Fairuz - Live", "tap", "video")]
        if self.page == "notes":
            return [("hint: Title", "text field, field, tap", "title"), ("hint: Note", "text field, field, tap", "note")]
        names = NAMES[self.top:self.top + 8]
        return [("(list)", "scrolls", "list")] + [(n, "tap", "contact") for n in names]

    def render(self):
        app = {"chat": "WhatsApp (com.whatsapp)", "notes": "Notes (com.notes)",
               "contacts": "Contacts (com.android.contacts)"}.get(self.page, "YouTube (com.google.android.youtube)")
        lines = ["App: " + app]
        for i, (label, tags, _) in enumerate(self.elements()):
            lines.append("[%d] %s%s" % (i + 1, label, (" · " + tags) if tags else ""))
        return "\n".join(lines)

    def __call__(self, action, timeout=90, **args):
        from . import phone, phone_fast
        self.calls.append((action, args))
        if action == "screen":
            return {"ok": True, "text": self.render()}
        els = self.elements()
        if action == "tap":
            if args.get("item"):
                label, tags, what = els[int(args["item"]) - 1]
            else:
                want = phone_fast._norm(args.get("text"))
                hit = [e for e in els if want and want in phone_fast._norm(e[0])]
                if not hit:
                    raise phone.PhoneError('nothing on the screen says "%s"' % args.get("text"))
                label, tags, what = hit[0]
            self.tap(label, what)
        elif action == "type":
            what = els[int(args["item"]) - 1][2] if args.get("item") else (
                "query" if self.page == "yt_search" else "field" if self.focused else None)
            if what not in ("field", "query", "title", "note"):
                raise phone.PhoneError("no text field to type into: tap one first")
            if what == "field":
                self.field = args.get("text") or ""
            elif what == "query":
                self.query = args.get("text") or ""
        elif action == "key":
            if not self.enter_works:
                raise phone.PhoneError("no field to press enter in (tap the button that sends instead)")
            if self.page == "yt_search" and self.query:
                self.submit()
        elif action == "scroll":
            self.top = min(self.top + 6, len(NAMES) - 8)
        return {"ok": True, "text": "done", "screen": self.render()}

    def tap(self, label, what):
        self.tapped.append(label)
        if what == "Send" and self.field:
            self.sent.append(self.field)
            self.field = ""
        elif what == "field":
            self.focused = True
        elif what == "open_search":
            self.page = "yt_search"
        elif what == "go" and self.query:
            self.submit()

    def submit(self):
        self.searched.append(self.query)
        self.page = "yt_results"


class HandsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = os.path.realpath(self.tmp.name)
        from . import settings
        for p in (mock.patch.object(settings, "HOME", os.path.join(self.root, "home")),
                  mock.patch.object(settings, "CONFIG", os.path.join(self.root, "home", "config.json"))):
            p.start()
            self.addCleanup(p.stop)
        self.fake = FakeApp()
        from . import phone
        for p in (mock.patch.object(phone, "call", self.fake), mock.patch.object(phone, "available", lambda: True)):
            p.start()
            self.addCleanup(p.stop)

    def agent(self):
        from . import agent, circuit, session
        a = agent.Agent(session.Session(self.root), client=SimpleNamespace(
            id="test", spec={}, local=False, on_device=False, context=lambda: 128000))
        self.addCleanup(a.memory.close)
        a.breaker = circuit.Breaker()
        return a

    def act(self, a, **args):
        from . import agent
        return tools.call(agent.ToolContext(a), "phone", args)

    def steps(self):
        return [c[0] for c in self.fake.calls if c[0] != "screen"]

    # ---------------------------------------------------------------- the tool
    def test_the_phone_tool_offers_send_and_search(self):
        t = tools.REGISTRY["phone"]
        self.assertTrue(getattr(t.fn, "_hands", False))
        self.assertIn("send", t.params["action"]["enum"])
        self.assertIn("search", t.params["action"]["enum"])
        self.assertIn("send (text: in an open chat", t.description)
        self.assertIn("scrolled to if further down", t.description)
        self.assertLess(len(json.dumps(t.schema())), 2000)           # a phone's small model reads it every thread
        self.assertTrue(getattr(t.fn, "_vital", False))             # the screen check inside stays known

    # ---------------------------------------------------------------- send
    def test_send_types_into_the_message_field_and_taps_send_in_one_call(self):
        from . import finish
        a = self.agent()
        out, meta = self.act(a, action="send", text="مرحبا يا أحمد")
        self.assertTrue(out.startswith('Sent: typed "مرحبا يا أحمد" into [2] and tapped [3] Send'), out)
        self.assertTrue(meta["sent"])
        self.assertIn("Screen now:\nApp: WhatsApp", out)
        self.assertEqual(self.fake.sent, ["مرحبا يا أحمد"])
        self.assertEqual(self.steps(), ["type", "tap"])
        # its steps are the turn's own: the end check sees a sent message, and a routine can be learned from them
        self.assertEqual(finish.check(a, "أرسلت الرسالة", False), "")
        self.assertTrue(a._phone_turn["verified"])

    def test_send_never_takes_send_money_for_send(self):
        a = self.agent()
        self.fake.buttons = ["Send money", "Send"]
        out, _ = self.act(a, action="send", text="hi")
        self.assertEqual(self.fake.sent, ["hi"])
        self.assertNotIn("Send money", self.fake.tapped)
        self.fake.buttons = ["Send money"]
        out, meta = self.act(a, action="send", text="hello")
        self.assertIn("no Send button is on the screen", out)
        self.assertFalse(meta["sent"])
        self.assertNotIn("Send money", self.fake.tapped)

    def test_send_asks_which_field_when_the_screen_has_several(self):
        a = self.agent()
        self.fake.page = "notes"
        with self.assertRaises(tools.ToolError) as e:
            self.act(a, action="send", text="hi")
        self.assertIn("several text fields on this screen ([1], [2])", str(e.exception))
        self.fake.page = "yt_home"
        with self.assertRaises(tools.ToolError) as e:
            self.act(a, action="send", text="hi")
        self.assertIn("no text field on this screen: open the chat first", str(e.exception))
        self.assertEqual(self.steps(), [])                           # nothing was typed anywhere

    # ---------------------------------------------------------------- search
    def test_search_taps_the_icon_types_and_presses_enter(self):
        a = self.agent()
        self.fake.page = "yt_home"
        out, meta = self.act(a, action="search", text="fairuz")
        self.assertEqual(self.fake.searched, ["fairuz"])
        self.assertTrue(meta["submitted"])
        self.assertTrue(out.startswith('Searched: tapped [2] (search); typed "fairuz" into [1]; pressed enter.'), out)
        self.assertIn("Fairuz - Live", out)
        self.assertEqual(self.steps(), ["tap", "type", "key"])

    def test_search_taps_the_search_button_when_enter_does_not_go(self):
        a = self.agent()
        self.fake.page, self.fake.enter_works = "yt_search", False
        out, _ = self.act(a, action="search", text="fairuz")
        self.assertEqual(self.fake.searched, ["fairuz"])
        self.assertIn("tapped [2] (search)", out)

    def test_search_never_types_into_a_message_field(self):
        a = self.agent()
        with self.assertRaises(tools.ToolError) as e:
            self.act(a, action="search", text="fairuz")
        self.assertIn("no search field or search button on this screen", str(e.exception))
        self.assertEqual(self.fake.field, "")
        self.assertEqual(self.steps(), [])

    # ---------------------------------------------------------------- a tap scrolls to its text
    def test_a_tap_on_a_text_further_down_scrolls_to_it(self):
        a = self.agent()
        self.fake.page = "contacts"
        out, _ = self.act(a, action="tap", text="زيد الخطيب")
        self.assertTrue(out.startswith("Scrolled down 3 times to find it."), out)
        self.assertEqual(self.fake.tapped, ["زيد الخطيب"])

    def test_a_tap_scrolls_no_further_than_the_end_of_the_list(self):
        a = self.agent()
        self.fake.page = "contacts"
        with self.assertRaises(tools.ToolError) as e:
            self.act(a, action="tap", text="Nobody")
        self.assertIn('nothing on the screen says "Nobody", even after scrolling down to the end of the list',
                      str(e.exception))
        self.assertEqual(self.steps().count("scroll"), 5)          # 4 that moved, 1 that found the end

    def test_a_tap_where_nothing_scrolls_fails_as_before(self):
        a = self.agent()
        with self.assertRaises(tools.ToolError) as e:
            self.act(a, action="tap", text="Nobody")
        self.assertNotIn("scrolling", str(e.exception))
        self.assertNotIn("scroll", self.steps())

    # ---------------------------------------------------------------- Arabic
    def test_arabic_digits_and_the_article(self):
        from . import phone_fast
        self.assertEqual(phone_fast._norm("الصفحة ٣ من ۱۲"), "الصفحه 3 من 12")
        self.assertEqual(phone_fast._bare("الكاميرا"), "كاميرا")
        self.assertEqual(phone_fast._bare("إلغاء"), "الغاء")            # a hamza, not the article
        self.assertEqual(phone_fast._bare("الله"), "الله")              # three letters would not be left
        self.assertEqual(phone_fast.app_name("كاميرا"), "camera")       # the table says "الكاميرا"
        self.assertEqual(phone_fast.app_name("إلغاء"), "إلغاء")

    @unittest.skipUnless(os.path.isdir(JAVA), "the Android sources are not next to this engine")
    def test_the_app_tries_again_without_the_article(self):
        with open(os.path.join(JAVA, "TextFold.java"), encoding="utf-8") as f:
            self.assertIn("static String bare(CharSequence text)", f.read())
        with open(os.path.join(JAVA, "Phone.java"), encoding="utf-8") as f:
            self.assertIn("String bareWant = TextFold.bare(name);", f.read())
        with open(os.path.join(JAVA, "PhoneControlService.java"), encoding="utf-8") as f:
            self.assertIn('String bareWant = TextFold.bare(a.optString("text"));', f.read())

    # ---------------------------------------------------------------- stability
    def test_pass_at_1_and_pass_hat_k(self):
        from . import stability
        rs = [{"id": "a", "ok": True}, {"id": "a", "ok": True}, {"id": "b", "ok": True}, {"id": "b", "ok": False}]
        s = stability.summarize(rs, 2)
        self.assertEqual(s["tasks"], {"a": {"passed": 2, "tries": 2}, "b": {"passed": 1, "tries": 2}})
        self.assertEqual((s["pass@1"], s["pass^2"]), (0.75, 0.5))

    def test_the_benchmark_runs_k_times_on_one_connection(self):
        from . import benchmark, models, stability
        client, seen = object(), []

        def run(model, ids, log=print, client=None):
            seen.append(client)
            ok = len(seen) != 2                                      # task y fails on the second try
            return {"results": [{"id": "x", "ok": True, "seconds": 1.0}, {"id": "y", "ok": ok, "seconds": 2.0}]}
        with mock.patch.object(models, "resolve", return_value={"id": "free-model"}), \
                mock.patch.object(models, "connect", return_value=client), \
                mock.patch.object(benchmark, "run", side_effect=run):
            s = stability.run("auto", None, 3, log=lambda *a: None)
        self.assertEqual(seen, [client] * 3)
        self.assertEqual((s["pass@1"], s["pass^3"]), (round(5 / 6.0, 3), 0.5))
        self.assertEqual(stability.line(s), "TOTAL 9.0 s, pass@1 83%, pass^3 50% (x 3/3 y 2/3)")
        out = io.StringIO()
        with mock.patch.object(stability, "run", return_value=s), redirect_stdout(out):
            self.assertEqual(benchmark.main(["--repeat", "3"]), 0)
        self.assertIn("pass^3 50%", out.getvalue())
