import os
import unittest
from unittest import mock

from . import runtime_manager


class RuntimeManagerTest(unittest.TestCase):
    def setUp(self):
        runtime_manager._clear_cache()

    def tearDown(self):
        runtime_manager._clear_cache()

    def test_android_native_is_adb_free(self):
        with mock.patch.object(runtime_manager, "_phone_available", return_value=True), \
             mock.patch.object(runtime_manager, "_termux_record", return_value={"status": "disconnected"}):
            data = runtime_manager.snapshot(False)
        native = data["runtimes"][0]
        self.assertEqual(native["runtime"], runtime_manager.ANDROID_NATIVE)
        self.assertFalse(native["requires_adb"])
        self.assertFalse(native["shell"])

    def test_android_command_probe_uses_localhost_bridge_not_android_path(self):
        environment = {
            "ok": True,
            "commands": {
                "node": {"available": True, "path": "/data/data/com.termux/files/usr/bin/node"},
                "npm": {"available": True, "path": "/data/data/com.termux/files/usr/bin/npm"},
                "npx": {"available": True, "path": "/data/data/com.termux/files/usr/bin/npx"},
                "python": {"available": True, "path": "/data/data/com.termux/files/usr/bin/python"},
                "git": {"available": True, "path": "/data/data/com.termux/files/usr/bin/git"},
                "bash": {"available": True, "path": "/data/data/com.termux/files/usr/bin/bash"},
            },
        }
        with mock.patch.object(runtime_manager, "_phone_available", return_value=True), \
             mock.patch.object(runtime_manager, "_termux_record", return_value={"status": "connected"}), \
             mock.patch.object(runtime_manager, "_ensure_bridge", return_value={"started_at": 7}), \
             mock.patch.object(runtime_manager, "_bridge_request", return_value=environment) as bridge, \
             mock.patch.object(runtime_manager, "_native") as native:
            state = runtime_manager.command_status("npx")
        self.assertEqual(state["runtime"], runtime_manager.TERMUX)
        self.assertTrue(state["available"])
        self.assertTrue(state["bridge"])
        self.assertIn("/environment?", bridge.call_args.args[1])
        native.assert_not_called()

    def test_disconnected_termux_is_unknown_not_false_missing_and_clears_cache(self):
        runtime_manager._CACHE_AT = 999999999.0
        runtime_manager._CACHE_STATE = "connected:old"
        runtime_manager._CACHE_VALUES = {"npx": True}
        with mock.patch.object(runtime_manager, "_phone_available", return_value=True), \
             mock.patch.object(runtime_manager, "_termux_record",
                               return_value={"status": "disconnected", "error": "Test Termux connection first"}):
            state = runtime_manager.command_status("npx")
        self.assertIsNone(state["available"])
        self.assertEqual(state["runtime"], runtime_manager.TERMUX)
        self.assertFalse(state["bridge"])
        self.assertIn("Termux", state["reason"])
        self.assertEqual(runtime_manager._CACHE_VALUES, {})
        self.assertEqual(runtime_manager._CACHE_STATE, "")

    def test_runtime_exec_routes_android_shell_over_bridge(self):
        result = {
            "ok": True,
            "status": "completed",
            "exit_code": 0,
            "stdout": "11.20.0\n",
            "stderr": "",
            "command_success": True,
        }
        with mock.patch.object(runtime_manager, "_phone_available", return_value=True), \
             mock.patch.object(runtime_manager, "_termux_record", return_value={"status": "connected"}), \
             mock.patch.object(runtime_manager, "_ensure_bridge", return_value={"started_at": 1}), \
             mock.patch.object(runtime_manager, "_bridge_request", return_value=result) as bridge, \
             mock.patch.object(runtime_manager, "_native") as native:
            out = runtime_manager.execute("npx -v")
        self.assertEqual(out["runtime"], runtime_manager.TERMUX)
        self.assertEqual(out["exit_code"], 0)
        self.assertEqual(bridge.call_args.args[:2], ("POST", "/exec"))
        self.assertEqual(bridge.call_args.args[2]["command"], "npx -v")
        native.assert_not_called()

    def test_bootstrap_uses_termux_run_command_only_to_start_loopback_bridge(self):
        with mock.patch.object(runtime_manager, "_termux_record", return_value={"status": "connected"}), \
             mock.patch.object(runtime_manager, "_phone_key", return_value="phone-secret"), \
             mock.patch.object(runtime_manager, "_native",
                               return_value={"status": "completed", "exit_code": 0}) as native:
            runtime_manager._bootstrap_bridge()
        native.assert_called_once()
        self.assertEqual(native.call_args.args[0], "termux_exec")
        command = native.call_args.kwargs["command"]
        self.assertIn("127.0.0.1", command)
        self.assertIn(str(runtime_manager.BRIDGE_PORT), command)
        self.assertNotIn("adb ", command.lower())
        self.assertNotIn("wireless", command.lower())

    def test_process_lifecycle_uses_bridge_api(self):
        responses = [
            {"ok": True, "id": "abc", "pid": 123, "status": "running"},
            {"ok": True, "id": "abc", "pid": 123, "status": "running", "logs": "ready"},
            {"ok": True, "id": "abc", "pid": 123, "status": "stopped"},
        ]
        with mock.patch.object(runtime_manager, "_ensure_bridge", return_value={"started_at": 1}), \
             mock.patch.object(runtime_manager, "_bridge_request", side_effect=responses) as bridge:
            started = runtime_manager.process_start("sleep 30")
            status = runtime_manager.process_status("abc")
            stopped = runtime_manager.process_stop("abc")
        self.assertEqual(started["status"], "running")
        self.assertEqual(status["logs"], "ready")
        self.assertEqual(stopped["status"], "stopped")
        self.assertEqual([c.args[1].split("?")[0] for c in bridge.call_args_list],
                         ["/process/start", "/process/status", "/process/stop"])

    def test_android_native_refuses_shell_instead_of_using_adb(self):
        with self.assertRaisesRegex(Exception, "does not run shell commands or adb"):
            runtime_manager.execute("adb devices", runtime_manager.ANDROID_NATIVE)

    def test_remote_runtime_requires_https_origin(self):
        with mock.patch.dict(os.environ, {"NEWAL_REMOTE_RUNTIME_URL": "http://example.com"}, clear=True):
            cfg = runtime_manager._remote_config()
        self.assertFalse(cfg["configured"])
        with mock.patch.dict(os.environ, {"NEWAL_REMOTE_RUNTIME_URL": "https://example.com/"}, clear=True):
            cfg = runtime_manager._remote_config()
        self.assertTrue(cfg["configured"])

    def test_bridge_origin_is_loopback_only(self):
        with mock.patch.dict(os.environ, {"MUSABAI_TERMUX_BRIDGE_URL": "http://example.com:8799"}, clear=True):
            with self.assertRaisesRegex(Exception, "loopback"):
                runtime_manager._bridge_origin()
        with mock.patch.dict(os.environ, {"MUSABAI_TERMUX_BRIDGE_URL": "http://127.0.0.1:8799"}, clear=True):
            self.assertEqual(runtime_manager._bridge_origin(), "http://127.0.0.1:8799")


if __name__ == "__main__":
    unittest.main()
