import os
import tempfile
import unittest
from types import SimpleNamespace
from unittest import mock

from . import mcp_bundles, mcp_config, settings


class McpBundlesTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = self.temp.name
        self.env = mock.patch.object(settings, "HOME", os.path.join(self.root, "private"))
        self.env.start()
        self.addCleanup(self.env.stop)

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
        self.assertEqual(catalog["playwright"]["status"], "runtime_missing")
        self.assertEqual(catalog["browser-use"]["status"], "runtime_missing")
        self.assertEqual(catalog["open-browser-use"]["status"], "runtime_missing")
        self.assertEqual(catalog["docling"]["status"], "runtime_missing")
        self.assertEqual(catalog["filesystem"]["status"], "runtime_missing")
        self.assertEqual(catalog["memory"]["status"], "runtime_missing")
        self.assertEqual(catalog["android"]["status"], "runtime_missing")
        self.assertEqual(catalog["github"]["status"], "credentials_missing")
        self.assertFalse(any(item["enabled"] for item in catalog.values()))

    def test_termux_npx_ready_is_not_reported_as_npx_missing(self):
        ready = {
            "runtime": runtime_manager.TERMUX,
            "missing": [],
            "unknown": [],
            "reason": "npx verified inside Termux",
            "stdio": False,
        }
        with mock.patch.object(runtime_manager, "requirements", return_value=ready):
            catalog = {item["id"]: item for item in mcp_bundles.catalog(self.root)}
        self.assertEqual(catalog["playwright"]["status"], "bridge_required")
        self.assertEqual(catalog["playwright"]["missing"], [])
        self.assertEqual(catalog["playwright"]["runtime"], runtime_manager.TERMUX)
        self.assertFalse(catalog["playwright"]["available"])

    def test_filesystem_and_memory_are_scoped_to_current_project(self):
        fs = mcp_bundles._spec(mcp_bundles._item("filesystem"), self.root)
        memory = mcp_bundles._spec(mcp_bundles._item("memory"), self.root)
        self.assertEqual(fs["args"][-1], os.path.realpath(self.root))
        memory_file = memory["env"]["MEMORY_FILE_PATH"]
        self.assertTrue(memory_file.startswith(os.path.realpath(self.root) + os.sep))
        self.assertTrue(memory_file.endswith(os.path.join(".newal", "mcp-memory.jsonl")))

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
        self.assertEqual(self.response, ({"ok": True, "tools": 17, "enabled": True}, 200))
        saved = mcp_config.read(self.root)
        self.assertEqual(saved["playwright"]["bundle"], "playwright")
        self.assertEqual(saved["playwright"]["tools"], 17)

        mcp_bundles.route(handler, "POST", "/api/mcp-bundles/disable",
                          {"session": "session1", "id": "playwright"})
        self.assertEqual(self.response, ({"ok": True}, 200))
        self.assertNotIn("playwright", mcp_config.read(self.root))

    def test_failed_handshake_never_claims_enabled(self):
        handler = SimpleNamespace(service=SimpleNamespace(get=lambda sid: SimpleNamespace(root=self.root)))
        handler._json = lambda data, status=200: setattr(self, "response", (data, status))
        with mock.patch.object(mcp_bundles, "_test", side_effect=RuntimeError("handshake failed")):
            mcp_bundles.route(handler, "POST", "/api/mcp-bundles/enable",
                              {"session": "session1", "id": "memory"})
        self.assertEqual(self.response[1], 400)
        self.assertNotIn("memory", mcp_config.read(self.root))


if __name__ == "__main__":
    unittest.main()
