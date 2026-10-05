import unittest
from types import SimpleNamespace
from unittest import mock

from . import freellmapi


class FreeLlmApiTests(unittest.TestCase):
    def handler(self):
        h = SimpleNamespace()
        h._json = lambda data, status=200: setattr(self, "response", (data, status))
        return h

    def test_status_is_forwarded_without_credentials(self):
        h = self.handler()
        with mock.patch.object(freellmapi.phone, "call", return_value={
            "ok": True,
            "up": True,
            "termux_installed": True,
            "termux_allowed": True,
            "endpoint": "http://127.0.0.1:3001/v1",
            "dashboard": "http://127.0.0.1:3001/",
        }):
            self.assertTrue(freellmapi.route(h, "GET", "/api/freellmapi"))
        self.assertEqual(self.response[1], 200)
        self.assertTrue(self.response[0]["up"])
        self.assertNotIn("key", repr(self.response[0]).lower())

    def test_setup_uses_phone_bridge_only(self):
        h = self.handler()
        calls = []

        def call(action, timeout=30):
            calls.append((action, timeout))
            return {"ok": True, "launched": True}

        with mock.patch.object(freellmapi.phone, "call", side_effect=call):
            freellmapi.route(h, "POST", "/api/freellmapi/setup", {})
        self.assertEqual(calls, [("freellmapi_setup", 30)])
        self.assertEqual(self.response, ({"ok": True, "launched": True}, 200))

    def test_phone_failure_is_visible_but_bounded(self):
        h = self.handler()
        with mock.patch.object(freellmapi.phone, "call", side_effect=freellmapi.phone.PhoneError("not available")):
            freellmapi.route(h, "POST", "/api/freellmapi/start", {})
        self.assertEqual(self.response[1], 400)
        self.assertIn("not available", self.response[0]["error"])


if __name__ == "__main__":
    unittest.main()
