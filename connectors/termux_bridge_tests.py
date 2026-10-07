import json
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request

from . import termux_bridge_server


TOKEN = "test-token-" + "a" * 48


class TermuxBridgeServerTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.server = termux_bridge_server.make_server("127.0.0.1", 0, TOKEN, self.temp.name)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = "http://127.0.0.1:%d" % self.server.server_address[1]

    def tearDown(self):
        if self.server is not None:
            self.server.shutdown()
            self.server.server_close()
            self.thread.join(2)

    def request(self, path, body=None, token=TOKEN, base=None):
        data = None if body is None else json.dumps(body).encode("utf-8")
        headers = {"X-MusabAI-Token": token}
        if data is not None:
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request((base or self.base) + path, data=data, headers=headers)
        with urllib.request.urlopen(req, timeout=3) as response:
            return json.load(response)

    def test_auth_health_and_environment(self):
        with self.assertRaises(urllib.error.HTTPError) as denied:
            self.request("/health", token="wrong")
        self.assertEqual(denied.exception.code, 401)
        health = self.request("/health")
        self.assertTrue(health["ok"])
        self.assertEqual(health["bridge"], "musabai-termux")
        env = self.request("/environment?commands=python,bash,definitely_missing_command")
        self.assertTrue(env["commands"]["python"]["available"])
        self.assertTrue(env["commands"]["bash"]["available"])
        self.assertFalse(env["commands"]["definitely_missing_command"]["available"])

    def test_exec_returns_structured_json(self):
        out = self.request("/exec", {"command": "printf bridge-ok"})
        self.assertEqual(out["status"], "completed")
        self.assertEqual(out["exit_code"], 0)
        self.assertEqual(out["stdout"], "bridge-ok")
        self.assertTrue(out["command_success"])

    def test_process_survives_bridge_restart_and_can_be_stopped(self):
        started = self.request("/process/start", {"command": "echo started; sleep 30"})
        self.assertEqual(started["status"], "running")
        process_id = started["id"]
        deadline = time.time() + 2
        while time.time() < deadline:
            if "started" in self.request("/process/status?id=" + process_id)["logs"]:
                break
            time.sleep(0.05)

        original = self.server
        original.shutdown()
        original.server_close()
        self.thread.join(2)

        replacement = termux_bridge_server.make_server("127.0.0.1", 0, TOKEN, self.temp.name)
        thread = threading.Thread(target=replacement.serve_forever, daemon=True)
        thread.start()
        base = "http://127.0.0.1:%d" % replacement.server_address[1]
        try:
            status = self.request("/process/status?id=" + process_id, base=base)
            self.assertEqual(status["status"], "running")
            stopped = self.request("/process/stop", {"id": process_id}, base=base)
            self.assertEqual(stopped["status"], "stopped")
            after = self.request("/process/status?id=" + process_id, base=base)
            self.assertEqual(after["status"], "stopped")
        finally:
            replacement.shutdown()
            replacement.server_close()
            thread.join(2)
            for proc in original.bridge_state._procs.values():
                try:
                    proc.wait(timeout=2)
                except Exception:
                    pass
            self.server = None


if __name__ == "__main__":
    unittest.main()
