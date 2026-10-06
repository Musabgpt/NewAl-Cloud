import unittest
from unittest import mock

from . import browser_router


class BrowserRouterTest(unittest.TestCase):
    def state(self, accounts=None, servers=None):
        accounts = accounts or []
        servers = servers or {}
        return mock.patch.multiple(
            browser_router,
            _connected_accounts=mock.DEFAULT,
            _saved_mcp=mock.DEFAULT,
        ), accounts, servers

    def test_connected_api_wins_before_browser_automation(self):
        accounts = {"github": {"id": "github", "status": "connected"}}
        with mock.patch.object(browser_router, "_connected_accounts", return_value=accounts),              mock.patch.object(browser_router, "_saved_mcp", return_value={
                 "playwright": {"bundle": "playwright", "tools": 18},
                 "browser-use": {"bundle": "browser-use", "tools": 12},
             }):
            result = browser_router.select("/project", target="https://github.com/org/repo")
        self.assertEqual(result["route"], "api")
        self.assertEqual(result["provider"], "github")

    def test_service_specific_mcp_wins_before_generic_browser(self):
        accounts = {"notionmcp": {"id": "notionmcp", "status": "connected"}}
        with mock.patch.object(browser_router, "_connected_accounts", return_value=accounts),              mock.patch.object(browser_router, "_saved_mcp", return_value={
                 "playwright": {"bundle": "playwright", "tools": 18},
             }):
            result = browser_router.select("/project", service="Notion")
        self.assertEqual(result["route"], "mcp")
        self.assertEqual(result["provider"], "notionmcp")

    def test_playwright_is_default_browser_route(self):
        with mock.patch.object(browser_router, "_connected_accounts", return_value={}),              mock.patch.object(browser_router, "_saved_mcp", return_value={
                 "playwright": {"bundle": "playwright", "tools": 18},
                 "browser-use": {"bundle": "browser-use", "tools": 12},
                 "open-browser-use": {"bundle": "open-browser-use", "tools": 5},
             }):
            result = browser_router.select("/project", target="https://example.com", structured_ui=True)
        self.assertEqual(result["route"], "playwright")
        self.assertEqual(result["tool_prefix"], "mcp__playwright__")

    def test_complex_ui_falls_back_to_browser_use(self):
        with mock.patch.object(browser_router, "_connected_accounts", return_value={}),              mock.patch.object(browser_router, "_saved_mcp", return_value={
                 "playwright": {"bundle": "playwright", "tools": 18},
                 "browser-use": {"bundle": "browser-use", "tools": 12},
             }):
            result = browser_router.select("/project", complex_ui=True, structured_ui=False)
        self.assertEqual(result["route"], "browser-use")

    def test_existing_signed_in_session_selects_open_browser_use(self):
        with mock.patch.object(browser_router, "_connected_accounts", return_value={}),              mock.patch.object(browser_router, "_saved_mcp", return_value={
                 "playwright": {"bundle": "playwright", "tools": 18},
                 "browser-use": {"bundle": "browser-use", "tools": 12},
                 "open-browser-use": {"bundle": "open-browser-use", "tools": 5},
             }):
            result = browser_router.select("/project", requires_existing_session=True)
        self.assertEqual(result["route"], "open-browser-use")

    def test_disabled_or_unverified_bundles_are_never_selected(self):
        with mock.patch.object(browser_router, "_connected_accounts", return_value={}),              mock.patch.object(browser_router, "_saved_mcp", return_value={
                 "playwright": {"bundle": "playwright", "tools": 0},
                 "browser-use": {"bundle": "browser-use", "tools": 0},
             }):
            result = browser_router.select("/project")
        self.assertFalse(result["available"])
        self.assertEqual(result["route"], "unavailable")
        self.assertEqual(result["setup_order"], ["playwright", "browser-use", "open-browser-use"])


if __name__ == "__main__":
    unittest.main()
