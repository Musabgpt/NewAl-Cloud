import unittest
from unittest import mock
from . import mcp_bundles


class McpBundlesTest(unittest.TestCase):
    def test_official_repositories_are_real_and_catalog_is_honest(self):
        ids = {item["id"] for item in mcp_bundles.BUNDLES}
        self.assertIn("playwright", ids)
        self.assertIn("reference-filesystem", ids)
        self.assertTrue(all(item["repository"].startswith("https://github.com/") for item in mcp_bundles.BUNDLES))
        with mock.patch("connectors.mcp_bundles.shutil.which", return_value=None):
            self.assertTrue(all(item["status"] == "runtime_missing" for item in mcp_bundles.catalog()))


if __name__ == "__main__":
    unittest.main()

