"""A Facebook Page connected in the app (facebook_page.py): its two tools are offered while it is connected (lean mode
too), they ask the app to post or to list the latest posts and never see the token, and a scheduled task about
Facebook runs through them with the screen off instead of opening the app."""
import os
import tempfile
import unittest
from types import SimpleNamespace
from unittest import mock

from . import tools  # noqa: F401 - registers every tool first, as the engine does


class FacebookTests(unittest.TestCase):
    def setUp(self):
        from . import connectors, phone, settings
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        os.makedirs(os.path.join(self.dir.name, "private"))
        self.page = {"id": "facebook", "name": "Facebook Page", "status": "connected", "account": "My Bakery",
                     "has_credentials": True}
        self.calls = []
        self.fail = None

        def call(action, timeout=90, **args):
            self.calls.append((action, args))
            if action != "connector":
                return {"ok": True}
            if args.get("op") == "status":
                return {"ok": True, "connectors": [self.page]}
            if self.fail:
                raise phone.PhoneError(self.fail)
            if args.get("op") == "post":
                return {"ok": True, "data": {"id": "42_7", "url": "https://www.facebook.com/42/posts/7",
                                             "page": "My Bakery"}}
            if args.get("op") == "recent":
                return {"ok": True, "data": {"page": "My Bakery", "posts": [
                    {"id": "42_6", "time": "2026-10-23T08:00:00+0000", "message": "صباح الخير يا جماعة",
                     "url": "https://www.facebook.com/42/posts/6"}]}}
            raise phone.PhoneError("unknown op")
        for p in (mock.patch.object(phone, "call", side_effect=call),
                  mock.patch.object(phone, "available", lambda: True),
                  mock.patch.object(settings, "HOME", os.path.join(self.dir.name, "private")),
                  mock.patch.object(connectors, "_cache", (0, []))):
            p.start()
            self.addCleanup(p.stop)
        self.ctx = SimpleNamespace(session=SimpleNamespace(id="s1", root=self.dir.name), agent=SimpleNamespace(depth=0),
                                   cancel=None, emit=lambda ev: None)

    def test_offered_only_while_the_page_is_connected(self):
        from . import connectors, lean
        names = connectors.names()
        self.assertIn("facebook_page_post", names)
        self.assertIn("facebook_page_recent", names)
        self.assertTrue(lean.connector("facebook_page_post"))           # on the phone too
        self.page["status"] = "disconnected"
        connectors._cache = (0, [])
        self.assertNotIn("facebook_page_post", connectors.names())

    def test_posts_through_the_app_without_the_token(self):
        from . import tools as t
        text, meta = t.call(self.ctx, "facebook_page_post", {"message": "منشور جديد", "link": "https://example.com"})
        self.assertIn("https://www.facebook.com/42/posts/7", text)
        self.assertEqual(meta["post"], "42_7")
        _, args = self.calls[-1]
        self.assertEqual(args, {"op": "post", "provider": "facebook", "message": "منشور جديد",
                                "link": "https://example.com"})
        self.assertEqual(t.REGISTRY["facebook_page_post"].kind, "connector_write")   # asks per the permission mode

    def test_latest_posts_and_errors(self):
        from . import tools as t
        text, meta = t.call(self.ctx, "facebook_page_recent", {"limit": 5})
        self.assertIn("صباح الخير يا جماعة", text)
        self.assertEqual(meta["posts"], 1)
        self.fail = "The Facebook Page's token expired: connect it again (Connections > Facebook Page)"
        with self.assertRaises(t.ToolError) as e:
            t.call(self.ctx, "facebook_page_post", {"message": "x"})
        self.assertIn("connect it again", str(e.exception))

    def test_a_facebook_task_runs_through_the_page_with_the_screen_off(self):
        from . import schedule
        task = schedule.add(SimpleNamespace(id="p", root=self.dir.name, model="auto", mode="auto-edit"),
                            "انشر منشور على فيسبوك عن عروض اليوم", schedule.when_of("daily", at="09:00"))
        p = schedule._public(task)
        self.assertEqual((p["via"], p["phone"]), (["facebook"], False))
        self.page["status"] = "disconnected"                             # not connected: the app, on the screen
        from . import connectors
        connectors._cache = (0, [])
        self.assertTrue(schedule._public(task)["phone"])


if __name__ == "__main__":
    unittest.main()
