"""The phone by sight and several steps in one call (phone_sight.py): screen_tap points on the whole screen, then on
a magnified crop, and taps the exact spot (the first point when the crop is not there); it says what is there when the
target is not; phone_steps runs actions back to back, checked, stopping at the first that fails."""
import os
import tempfile
import unittest
from types import SimpleNamespace
from unittest import mock

from . import tools  # noqa: F401 - registers every tool first, as the engine does


class FakeClient:
    def __init__(self, *answers, on_device=False):
        self.answers = list(answers)
        self.on_device = on_device
        self.seen = []

    def chat(self, msg, tools=None, owner=None, max_tokens=None, reasoning=None, cancel=None):
        self.seen.append(msg[0]["content"][0]["text"])
        return SimpleNamespace(content=self.answers.pop(0))


class SightTests(unittest.TestCase):
    def setUp(self):
        from . import phone
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.shot = os.path.join(self.dir.name, "musabai-screen-1.png")
        self.small = os.path.join(self.dir.name, "musabai-screen-1-small.jpg")
        self.crop = os.path.join(self.dir.name, "musabai-crop-1.jpg")
        for p in (self.shot, self.small, self.crop):
            with open(p, "wb") as f:
                f.write(b"\xff\xd8\xff\xe0 not really a picture")
        self.calls = []
        self.fail = {}
        self.no_crop = False
        self.screen = "App: WhatsApp (com.whatsapp)\n[1] Ahmad"

        def call(action, timeout=90, **args):
            self.calls.append((action, args))
            if action in self.fail:
                raise phone.PhoneError(self.fail[action])
            if action == "screenshot":
                return {"ok": True, "path": self.shot, "preview_path": self.small, "width": 1080, "height": 2400}
            if action == "image_crop":
                if self.no_crop:
                    raise phone.PhoneError('unknown action "image_crop"')
                return {"ok": True, "path": self.crop}
            if action == "screen":
                return {"ok": True, "text": self.screen}
            if action in ("tap", "type", "key"):
                return {"ok": True, "text": "%s done" % action, "screen": "App: WhatsApp (com.whatsapp)\n[1] Send"}
            return {"ok": True, "text": "%s done" % action}
        for p in (mock.patch.object(phone, "call", side_effect=call), mock.patch.object(phone, "available",
                                                                                      lambda: True)):
            p.start()
            self.addCleanup(p.stop)

    def ctx(self, client):
        agent = SimpleNamespace(client=client, session=SimpleNamespace(id="s1", turn=1), cancel=None, depth=0)
        return SimpleNamespace(agent=agent, session=agent.session, cancel=None, emit=lambda ev: None)

    def run_tool(self, name, client, **args):
        from . import tools as t
        return t.call(self.ctx(client), name, args)

    # ------------------------------------------------------------------ screen_tap

    def test_points_reads(self):
        from .phone_sight import parse
        self.assertEqual(parse('```json\n{"found": true, "x": 500, "y": 900}\n```'), ((500.0, 900.0), ""))
        self.assertEqual(parse('{"found": false, "why": "a login form, no + button"}'),
                         (None, "a login form, no + button"))
        self.assertIsNone(parse('{"found": true, "x": 1500, "y": 10}')[0])
        self.assertIsNone(parse('{"found": true}')[0])
        self.assertIsNone(parse("I cannot tell")[0])

    def test_taps_the_spot_found_on_the_magnified_crop(self):
        client = FakeClient('{"found": true, "x": 500, "y": 900}', '{"found": true, "x": 250, "y": 500}')
        text, meta = self.run_tool("screen_tap", client, target="the round + button at the bottom")
        # the whole screen: (540, 2160); the crop: 432 px square at (324, 1944); its point (250, 500) -> (432, 2160)
        self.assertIn(("image_crop", {"path": self.shot, "x": 324, "y": 1944, "w": 432, "h": 432, "max": 720}),
                      self.calls)
        self.assertIn(("tap", {"x": 432, "y": 2160}), self.calls)
        self.assertEqual((meta["x"], meta["y"], meta["exact"]), (432, 2160, True))
        self.assertIn("Screen now:", text)
        self.assertIn("a phone's screen", client.seen[0])
        self.assertIn("magnified", client.seen[1])

    def test_without_the_crop_the_first_point_is_tapped(self):
        self.no_crop = True                                      # an app without image_crop
        client = FakeClient('{"found": true, "x": 100, "y": 50}')
        text, meta = self.run_tool("screen_tap", client, target="the menu icon")
        self.assertIn(("tap", {"x": 108, "y": 120}), self.calls)
        self.assertFalse(meta["exact"])
        self.assertIn("less exact", text)

    def test_find_only_and_not_found(self):
        client = FakeClient('{"found": true, "x": 500, "y": 500}', '{"found": true, "x": 500, "y": 500}')
        text, meta = self.run_tool("screen_tap", client, target="the play button", action="find")
        self.assertNotIn("tap", [c for c, _ in self.calls])
        self.assertIn("is at 540,1200", text)
        self.screen = "App: Game (com.game)\n(nothing readable on this screen)"
        client = FakeClient('{"found": false, "why": "a paused video, no play button"}')
        text, meta = self.run_tool("screen_tap", client, target="the play button")
        self.assertFalse(meta["found"])
        self.assertIn("a paused video, no play button", text)
        self.assertIn("nothing readable", text)                  # and what the screen tool reads

    def test_needs_a_vision_model(self):
        from . import tools as t
        with self.assertRaises(t.ToolError):
            self.run_tool("screen_tap", FakeClient(on_device=True), target="the + button")

    # ------------------------------------------------------------------ phone_steps

    def test_steps_run_back_to_back(self):
        ctx = self.ctx(FakeClient())
        from . import phone_fast, tools as t
        text, meta = t.call(ctx, "phone_steps", {"steps": [
            {"action": "open_app", "name": "واتساب"}, {"action": "tap", "text": "Ahmad"},
            {"action": "type", "text": "مرحبا"}, {"action": "tap", "text": "Send"}]})
        acts = [(c, a) for c, a in self.calls if c != "screen"]
        self.assertEqual(acts, [("open_app", {"name": "com.whatsapp"}), ("tap", {"text": "Ahmad"}),
                                ("type", {"text": "مرحبا"}), ("tap", {"text": "Send"})])
        self.assertTrue(meta["done"])
        self.assertIn("[1] Send", text)
        self.assertEqual([a for a, _, ok in phone_fast._state(ctx)["log"]], ["open_app", "tap", "type", "tap"])

    def test_steps_stop_at_the_first_failure(self):
        self.fail["type"] = "no text field is focused"
        text, meta = self.run_tool("phone_steps", FakeClient(), steps=[
            {"action": "tap", "item": 3}, {"action": "type", "text": "hi"}, {"action": "key", "name": "enter"}])
        self.assertFalse(meta["done"])
        self.assertIn("Stopped at step 2 of 3", text)
        self.assertIn("no text field is focused", text)
        self.assertNotIn("key", [c for c, _ in self.calls])

    def test_steps_are_checked_first(self):
        from . import tools as t
        for steps in ([], [{"action": "rm -rf"}], [{"action": "tap", "item": 1}] * 13, "not json"):
            with self.assertRaises(t.ToolError):
                self.run_tool("phone_steps", FakeClient(), steps=steps)
        text, meta = self.run_tool("phone_steps", FakeClient(), steps=[{"action": "wait", "seconds": 1}])
        self.assertTrue(meta["done"])

    def test_offered_on_the_phone(self):
        from . import claude_parity, lean, tools as t
        for name in ("screen_tap", "phone_steps"):
            self.assertIn(name, lean.LEAN)
            self.assertIn(name, claude_parity.CORE)
            self.assertIn(name, t.REGISTRY)


if __name__ == "__main__":
    unittest.main()
