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

    def test_android_command_probe_uses_termux_not_android_path(self):
        result = {
            "status": "completed",
            "exit_code": 0,
            "stdout": "node=1\nnpm=1\nnpx=1\npython=1\ngit=1\nbash=1\n",
            "stderr": "",
            "command_success": True,
        }
        with mock.patch.object(runtime_manager, "_phone_available", return_value=True), \
             mock.patch.object(runtime_manager, "_termux_record", return_value={"status": "connected"}), \
             mock.patch.object(runtime_manager, "_native", return_value=result) as native:
            state = runtime_manager.command_status("npx")
        self.assertEqual(state["runtime"], runtime_manager.TERMUX)
        self.assertTrue(state["available"])
        self.assertEqual(native.call_args.args[0], "termux_exec")
        self.assertIn("command -v", native.call_args.kwargs["command"])

    def test_disconnected_termux_is_unknown_not_false_missing(self):
        with mock.patch.object(runtime_manager, "_phone_available", return_value=True), \
             mock.patch.object(runtime_manager, "_termux_record",
                               return_value={"status": "disconnected", "error": "Test Termux connection first"}):
            state = runtime_manager.command_status("npx")
        self.assertIsNone(state["available"])
        self.assertEqual(state["runtime"], runtime_manager.TERMUX)
        self.assertIn("Termux", state["reason"])

    def test_runtime_exec_routes_android_shell_to_termux(self):
        result = {
            "id": "job",
            "status": "completed",
            "exit_code": 0,
            "stdout": "11.20.0\n",
            "stderr": "",
            "command_success": True,
        }
        with mock.patch.object(runtime_manager, "_phone_available", return_value=True), \
             mock.patch.object(runtime_manager, "_termux_record", return_value={"status": "connected"}), \
             mock.patch.object(runtime_manager, "_native", return_value=result) as native:
            out = runtime_manager.execute("npx -v")
        self.assertEqual(out["runtime"], runtime_manager.TERMUX)
        native.assert_called_once_with("termux_exec", command="npx -v")

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


if __name__ == "__main__":
    unittest.main()
