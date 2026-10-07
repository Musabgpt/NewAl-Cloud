import os
import tempfile
import unittest
from types import SimpleNamespace
from unittest import mock

from . import mcp_bundles, mcp_config, runtime_manager, settings, tools


class McpBundlesTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = self.temp.name
        self.env = mock.patch.object(settings, "HOME", os.path.join(self.root, "private"))
        self.env.start()
        self.addCleanup(self.env.stop)
        mcp_bundles._RUNNING.clear()
        mcp_bundles._LAST_ERRORS.clear()

    def test_exact_requested_bundle_catalog_is_real_and_honest(self):
        ids = [item["id"] for item in mcp_bundles.BUNDLES]
        self.assertEqual(ids, ["playwright", "browser-use", "open-browser-use", "docling", "github", "filesystem", "android", "memory"])
        self.assertTrue(all(item["repository"].startswith("https://github.com/") for item in mcp_bundles.BUNDLES))

        def no_runtime(commands):
            return {
                "runtime": "LOCAL_HOST",
                "missing": list(commands),
                "unknown": [],
                "reason": "No command is installed on the test host.",
                "stdio": True,
            }

        with mock.patch.object(runtime_manager, "requirements", side_effect=no_runtime), \
             mock.patch.dict(os.environ, {}, clear=True):
            catalog = {item["id"]: item for item in mcp_bundles.catalog(self.root)}
        self.assertEqual(catalog["playwright"]["status"], "tool_missing")
        self.assertEqual(catalog["browser-use"]["status"], "tool_missing")
        self.assertEqual(catalog["open-browser-use"]["status"], "tool_missing")
        self.assertEqual(catalog["docling"]["status"], "tool_missing")
        self.assertEqual(catalog["filesystem"]["status"], "tool_missing")
        self.assertEqual(catalog["memory"]["status"], "tool_missing")
        self.assertEqual(catalog["android"]["status"], "tool_missing")
        self.assertEqual(catalog["github"]["status"], "permission_required")
        self.assertFalse(any(item["enabled"] for item in catalog.values()))

    def test_termux_npx_ready_is_not_reported_as_npx_missing(self):
        ready = {
            "runtime": runtime_manager.TERMUX,
            "missing": [],
            "unknown": [],
            "reason": "npx verified inside Termux",
            "stdio": True,
        }
        with mock.patch.object(runtime_manager, "requirements", return_value=ready):
            catalog = {item["id"]: item for item in mcp_bundles.catalog(self.root)}
        self.assertEqual(catalog["playwright"]["status"], "ready")
        self.assertEqual(catalog["playwright"]["missing"], [])
        self.assertEqual(catalog["playwright"]["runtime"], runtime_manager.TERMUX)
        self.assertTrue(catalog["playwright"]["available"])
        self.assertEqual(catalog["playwright"]["start_method"], "runtime_process_start(stdio=true)")
        self.assertEqual(catalog["playwright"]["stop_method"], "runtime_process_stop")
        self.assertEqual(catalog["playwright"]["health_check"], "live process status + MCP tools/list")

    def test_filesystem_and_memory_are_scoped_to_current_project(self):
        fs = mcp_bundles._spec(mcp_bundles._item("filesystem"), self.root)
        memory = mcp_bundles._spec(mcp_bundles._item("memory"), self.root)
        self.assertEqual(fs["args"][-1], os.path.realpath(self.root))
        memory_file = memory["env"]["MEMORY_FILE_PATH"]
        self.assertTrue(memory_file.startswith(os.path.realpath(self.root) + os.sep))
        self.assertTrue(memory_file.endswith(os.path.join(".newal", "mcp-memory.jsonl")))

    def test_memory_uses_project_scoped_file_inside_termux_home(self):
        ready = {
            "runtime": runtime_manager.TERMUX,
            "missing": [],
            "unknown": [],
            "reason": "npx verified inside Termux",
            "stdio": True,
        }
        with mock.patch.object(runtime_manager, "requirements", return_value=ready), \
             mock.patch.object(runtime_manager, "termux_home", return_value="/data/data/com.termux/files/home"):
            memory = mcp_bundles._spec(mcp_bundles._item("memory"), self.root)
        memory_file = memory["env"]["MEMORY_FILE_PATH"]
        self.assertTrue(memory_file.startswith("/data/data/com.termux/files/home/"))
        self.assertNotIn(os.path.realpath(self.root), memory_file)
        self.assertIn("musabai-mcp-memory-", memory_file)

    def test_filesystem_is_not_falsely_available_for_app_private_root_in_termux(self):
        ready = {
            "runtime": runtime_manager.TERMUX,
            "missing": [],
            "unknown": [],
            "reason": "npx verified inside Termux",
            "stdio": True,
        }
        with mock.patch.object(runtime_manager, "requirements", return_value=ready):
            catalog = {item["id"]: item for item in mcp_bundles.catalog(self.root)}
        self.assertEqual(catalog["filesystem"]["status"], "needs_setup")
        self.assertFalse(catalog["filesystem"]["available"])

    def test_phase2_browser_bundle_commands_are_pinned_and_explicit(self):
        playwright = mcp_bundles._spec(mcp_bundles._item("playwright"), self.root)
        browser_use = mcp_bundles._spec(mcp_bundles._item("browser-use"), self.root)
        obu = mcp_bundles._spec(mcp_bundles._item("open-browser-use"), self.root)
        self.assertEqual(playwright["command"], "npx")
        self.assertIn("@playwright/mcp@0.0.83", playwright["args"])
        self.assertIn("--isolated", playwright["args"])
        self.assertEqual(browser_use, {
            "command": "uvx",
            "args": ["browser-use==0.13.5", "--cli-mcp"],
            "env": {},
        })
        self.assertEqual(obu, {
            "command": "obu",
            "args": ["mcp", "stdio"],
            "env": {},
        })

    def test_docling_bundle_is_pinned_to_reviewed_local_stdio_contract(self):
        docling = mcp_bundles._spec(mcp_bundles._item("docling"), self.root)
        self.assertEqual(docling["command"], "uvx")
        self.assertEqual(docling["args"], [
            "--from", "docling-mcp[local]==3.3.0", "docling-mcp-server", "--transport", "stdio"
        ])
        self.assertEqual(docling["env"]["DOCLING_MCP_CONVERSION_MODE"], "local")
        self.assertEqual(docling["env"]["DOCLING_MCP_KEEP_IMAGES"], "false")

    def test_github_token_is_only_in_child_process_environment(self):
        item = mcp_bundles._item("github")
        with mock.patch.dict(os.environ, {"GH_TOKEN": "private-test-token"}, clear=True):
            spec = mcp_bundles._spec(item, self.root)
        self.assertEqual(spec["env"]["GITHUB_PERSONAL_ACCESS_TOKEN"], "private-test-token")
        public = mcp_bundles.catalog(self.root)
        self.assertNotIn("private-test-token", repr(public))

    def test_enable_persists_only_after_successful_real_handshake(self):
        handler = SimpleNamespace(service=SimpleNamespace(get=lambda sid: SimpleNamespace(root=self.root)))
        handler._json = lambda data, status=200: setattr(self, "response", (data, status))
        handler._query = lambda: {"session": "session1"}

        with mock.patch.object(mcp_bundles, "_test", return_value=17):
            self.assertTrue(mcp_bundles.route(
                handler, "POST", "/api/mcp-bundles/enable",
                {"session": "session1", "id": "playwright"},
            ))
        self.assertEqual(self.response, ({"ok": True, "tools": 17, "enabled": True, "running": False}, 200))
        saved = mcp_config.read(self.root)
        self.assertEqual(saved["playwright"]["bundle"], "playwright")
        self.assertEqual(saved["playwright"]["tools"], 17)
        catalog = {item["id"]: item for item in mcp_bundles.catalog(self.root)}
        self.assertEqual(catalog["playwright"]["status"], "server_stopped")
        self.assertTrue(catalog["playwright"]["installed"])
        self.assertFalse(catalog["playwright"]["connected"])

        mcp_bundles.route(handler, "POST", "/api/mcp-bundles/disable",
                          {"session": "session1", "id": "playwright"})
        self.assertEqual(self.response, ({"ok": True, "enabled": False, "running": False}, 200))
        self.assertNotIn("playwright", mcp_config.read(self.root))

    def test_start_stop_and_reconnect_control_the_real_managed_process(self):
        ready = {
            "runtime": runtime_manager.TERMUX,
            "missing": [],
            "unknown": [],
            "reason": "Termux bridge verified",
            "stdio": True,
        }

        class FakeServer:
            starts = 0

            def __init__(self, name, spec, cwd):
                self.name = name
                self.spec = spec
                self.cwd = cwd
                self._termux = True
                self._termux_process_id = ""
                self.tools = []

            def start(self, timeout=45):
                type(self).starts += 1
                self._termux_process_id = "mcp-%d" % type(self).starts
                self.tools = [{"name": "tool", "inputSchema": {"type": "object"}}]
                return self

            def alive(self):
                return bool(self._termux_process_id)

            def _list_tools(self):
                return list(self.tools) or [{"name": "tool", "inputSchema": {"type": "object"}}]

            def stop(self):
                self._termux_process_id = ""

        item = mcp_bundles._item("playwright")
        with mock.patch.object(mcp_bundles, "_test", return_value=1):
            mcp_bundles._save_enabled(item, self.root, 1)

        with mock.patch.object(runtime_manager, "requirements", return_value=ready), \
             mock.patch.object(mcp_config, "StdioServer", FakeServer), \
             mock.patch.object(runtime_manager, "process_stop", return_value={"ok": True}) as process_stop:
            started = mcp_bundles.perform(self.root, "playwright", "start")
            self.assertTrue(started["running"])
            catalog = {row["id"]: row for row in mcp_bundles.catalog(self.root)}
            self.assertEqual(catalog["playwright"]["status"], "server_running")
            self.assertTrue(catalog["playwright"]["connected"])
            self.assertTrue(catalog["playwright"]["running"])
            self.assertTrue(catalog["playwright"]["process_id"].startswith("mcp-"))

            stopped = mcp_bundles.perform(self.root, "playwright", "stop")
            self.assertFalse(stopped["running"])
            process_stop.assert_called_once()
            catalog = {row["id"]: row for row in mcp_bundles.catalog(self.root)}
            self.assertEqual(catalog["playwright"]["status"], "server_stopped")
            self.assertFalse(catalog["playwright"]["connected"])

            reconnected = mcp_bundles.perform(self.root, "playwright", "reconnect")
            self.assertTrue(reconnected["running"])
            catalog = {row["id"]: row for row in mcp_bundles.catalog(self.root)}
            self.assertEqual(catalog["playwright"]["status"], "server_running")

    def test_running_process_can_be_reattached_from_persisted_runtime_state(self):
        ready = {
            "runtime": runtime_manager.TERMUX,
            "missing": [],
            "unknown": [],
            "reason": "Termux bridge verified",
            "stdio": True,
        }

        class AttachedServer:
            def __init__(self, name, spec, cwd):
                self._termux = False
                self._termux_process_id = ""
                self.tools = []

            def alive(self):
                return self._termux and self._termux_process_id == "persisted-1"

        item = mcp_bundles._item("playwright")
        mcp_bundles._save_enabled(item, self.root, 2)
        mcp_bundles._save_runtime_state(self.root, {
            "playwright": {"process_id": "persisted-1", "started_at": 1}
        })
        mcp_bundles._RUNNING.clear()
        with mock.patch.object(runtime_manager, "requirements", return_value=ready), \
             mock.patch.object(mcp_config, "StdioServer", AttachedServer):
            catalog = {row["id"]: row for row in mcp_bundles.catalog(self.root)}
        self.assertEqual(catalog["playwright"]["status"], "server_running")
        self.assertEqual(catalog["playwright"]["process_id"], "persisted-1")

    def test_failed_handshake_never_claims_enabled(self):
        handler = SimpleNamespace(service=SimpleNamespace(get=lambda sid: SimpleNamespace(root=self.root)))
        handler._json = lambda data, status=200: setattr(self, "response", (data, status))
        with mock.patch.object(mcp_bundles, "_test", side_effect=RuntimeError("handshake failed")):
            mcp_bundles.route(handler, "POST", "/api/mcp-bundles/enable",
                              {"session": "session1", "id": "memory"})
        self.assertEqual(self.response[1], 400)
        self.assertNotIn("memory", mcp_config.read(self.root))

    def test_termux_bridge_tool_error_is_returned_as_json_not_dropped_connection(self):
        handler = SimpleNamespace(service=SimpleNamespace(get=lambda sid: SimpleNamespace(root=self.root)))
        handler._json = lambda data, status=200: setattr(self, "response", (data, status))
        with mock.patch.object(mcp_bundles, "_test", side_effect=tools.ToolError("stdio request timed out")):
            self.assertTrue(mcp_bundles.route(
                handler, "POST", "/api/mcp-bundles/enable",
                {"session": "session1", "id": "playwright"},
            ))
        self.assertEqual(self.response[1], 400)
        self.assertIn("stdio request timed out", self.response[0]["error"])
        self.assertNotIn("playwright", mcp_config.read(self.root))


if __name__ == "__main__":
    unittest.main()
