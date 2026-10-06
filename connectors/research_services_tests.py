import io
import json
import tempfile
import unittest
from types import SimpleNamespace
from unittest import mock

from . import research_services, settings, tools


class ResearchServicesTest(unittest.TestCase):
    def test_service_url_validation_rejects_remote_plain_http_and_embedded_credentials(self):
        self.assertEqual(research_services._base("https://search.example.com/"), "https://search.example.com")
        self.assertEqual(research_services._base("http://127.0.0.1:8080/"), "http://127.0.0.1:8080")
        with self.assertRaises(ValueError):
            research_services._base("http://search.example.com")
        with self.assertRaises(ValueError):
            research_services._base("https://user:secret@search.example.com")
        with self.assertRaises(ValueError):
            research_services._base("https://search.example.com/?token=x")

    def test_searxng_results_are_normalized_and_limited(self):
        payload = {
            "results": [
                {"title": "One", "url": "https://one.example", "content": "alpha"},
                {"title": "Bad", "url": "javascript:alert(1)", "content": "skip"},
                {"title": "Two", "url": "https://two.example", "content": "beta"},
            ]
        }
        with mock.patch.object(research_services, "_config", return_value={"searxng_url": "https://search.example"}), \
             mock.patch.object(research_services, "_request", return_value=payload) as request:
            rows = research_services.searxng_search("hello", 2)
        self.assertEqual([x["title"] for x in rows], ["One", "Two"])
        self.assertEqual(rows[0]["snippet"], "alpha")
        self.assertIn("format=json", request.call_args.args[0])

    def test_crawl4ai_normalizes_markdown_without_exposing_token(self):
        payload = {
            "success": True,
            "results": [{"success": True, "markdown": {"raw_markdown": "# Example\nBody"}}],
        }
        with mock.patch.object(research_services, "_config", return_value={"crawl4ai_url": "https://crawl.example"}), \
             mock.patch.object(research_services, "_secret", return_value="private-token"), \
             mock.patch.object(research_services, "_request", return_value=payload) as request:
            text = research_services.crawl4ai_fetch("https://example.com")
        self.assertEqual(text, "# Example\nBody")
        kwargs = request.call_args.kwargs
        self.assertEqual(kwargs["token"], "private-token")
        self.assertNotIn("private-token", repr(research_services.public_status()))

    def test_builtin_search_prefers_searxng_when_available(self):
        expected = [{"title": "Private metasearch", "url": "https://example.com", "snippet": "result"}]
        with mock.patch.object(research_services, "searxng_search", return_value=expected):
            self.assertEqual(tools.web_search("anything"), expected)

    def test_builtin_fetch_falls_back_to_crawl4ai_after_http_failure(self):
        ctx = SimpleNamespace()
        with mock.patch.object(tools.urllib.request, "urlopen", side_effect=OSError("blocked")), \
             mock.patch.object(research_services, "crawl4ai_fetch", return_value="# crawled\ncontent"):
            text, meta = tools.t_web_fetch(ctx, "https://example.com")
        self.assertIn("crawled", text)
        self.assertEqual(meta["backend"], "crawl4ai")

    def test_public_status_never_returns_secure_token(self):
        with mock.patch.object(research_services, "_config", return_value={
            "searxng_url": "https://search.example",
            "crawl4ai_url": "https://crawl.example",
        }), mock.patch.object(research_services, "_secret_status", return_value=True):
            status = research_services.public_status()
        self.assertTrue(status["crawl4ai"]["token_configured"])
        self.assertNotIn("token", json.dumps(status).replace("token_configured", ""))


if __name__ == "__main__":
    unittest.main()
