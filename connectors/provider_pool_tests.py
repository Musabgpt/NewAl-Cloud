import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from . import provider_pool, provider_keys, providers


class ProviderPoolTests(unittest.TestCase):
    def setUp(self):
        provider_pool.reset_health()

    def test_free_pool_order_and_current_provider_is_not_repeated(self):
        c = SimpleNamespace(
            spec={"id": "current", "base_url": "https://current.example/v1"},
            model_name="current",
            provider=None,
        )
        env = {
            "GROQ_API_KEY": "g",
            "GEMINI_API_KEY": "m",
            "OPENROUTER_API_KEY": "o",
            "NVIDIA_API_KEY": "n",
        }
        with patch.dict(os.environ, env, clear=True), patch.object(provider_pool.settings, "user", return_value={}):
            ids = [x["id"] for x in provider_pool.candidates(c)]
        self.assertEqual(ids, [
            "groq/gpt-oss-120b-free",
            "gemini/3.7-flash-free",
            "openrouter/free",
            "nvidia/nemotron-3-ultra-free",
        ])

    def test_skips_services_without_credentials(self):
        c = SimpleNamespace(spec={"id": "current"}, model_name="current", provider=None)
        with patch.dict(os.environ, {}, clear=True), patch.object(provider_pool.settings, "user", return_value={}):
            self.assertEqual(provider_pool.candidates(c), [])

    def test_android_keystore_credentials_feed_the_free_pool(self):
        c = SimpleNamespace(spec={"id": "current"}, model_name="current", provider=None)
        with patch.dict(os.environ, {}, clear=True), \
             patch.object(provider_keys, "secret", return_value="vault-secret-key"), \
             patch.object(provider_pool.settings, "user", return_value={}):
            ids = [x["id"] for x in provider_pool.candidates(c)]
        self.assertEqual(ids, [
            "freellmapi/auto",
            "groq/gpt-oss-120b-free",
            "gemini/3.7-flash-free",
            "openrouter/free",
            "nvidia/nemotron-3-ultra-free",
        ])

    def test_paid_custom_fallback_is_never_silently_used(self):
        c = SimpleNamespace(spec={"id": "current"}, model_name="current", provider=None)
        configured = [
            {"id": "paid", "base_url": "https://paid.example/v1", "api_key": "x", "model": "expensive"},
            {"id": "free-custom", "base_url": "https://free.example/v1", "api_key": "x", "model": "free", "free": True},
        ]
        with patch.dict(os.environ, {}, clear=True), patch.object(
                provider_pool.settings, "user", return_value={"fallback_models": configured}):
            ids = [x["id"] for x in provider_pool.candidates(c)]
        self.assertEqual(ids, ["free-custom"])

    def test_switches_after_overload_and_reports_real_target(self):
        class Bad:
            def chat(self, *a, **k):
                raise providers.ProviderError("overloaded", 503)

        class Good:
            def chat(self, *a, **k):
                return "ok"

        c = SimpleNamespace(
            spec={"id": "nvidia", "base_url": "https://integrate.api.nvidia.com/v1"},
            model_name="nvidia",
            provider=Bad(),
        )
        backup = {
            "id": "backup/free",
            "model": "backup",
            "base_url": "https://x.example/v1",
            "provider": "openai",
            "free": True,
        }
        with patch.object(provider_pool, "candidates", return_value=[backup]),              patch.object(provider_pool, "provider", return_value=Good()),              patch.object(provider_pool.time, "sleep", return_value=None),              patch.object(provider_pool.random, "random", return_value=0):
            self.assertEqual(provider_pool.chat(c, [], tools=[]), "ok")
        self.assertEqual(c.model_name, "backup")
        self.assertEqual(c._last_fallback["to"], "backup/free")

    def test_overloaded_provider_enters_cooldown_and_is_skipped(self):
        spec = {
            "id": "groq/gpt-oss-120b-free",
            "base_url": "https://api.groq.com/openai/v1",
            "model": "openai/gpt-oss-120b",
            "api_key": "g",
            "free": True,
        }
        provider_pool._mark_failure(spec, providers.ProviderError("overloaded", 503))
        c = SimpleNamespace(spec={"id": "current"}, model_name="current", provider=None)
        with patch.dict(os.environ, {"GROQ_API_KEY": "g"}, clear=True), patch.object(
                provider_pool.settings, "user", return_value={}):
            ids = [x["id"] for x in provider_pool.candidates(c)]
        self.assertNotIn("groq/gpt-oss-120b-free", ids)
        self.assertTrue(provider_pool.health_snapshot()["groq/gpt-oss-120b-free"]["cooling_down"])

    def test_does_not_fail_over_after_visible_stream_output(self):
        class Partial:
            def chat(self, *a, **k):
                k["on_event"]("text", "hello")
                raise providers.ProviderError("connection reset")

        c = SimpleNamespace(spec={"id": "current"}, model_name="current", provider=Partial())
        seen = []
        with patch.object(provider_pool, "candidates") as candidates,              patch.object(provider_pool.time, "sleep", return_value=None):
            with self.assertRaises(providers.ProviderError):
                provider_pool.chat(c, [], on_event=lambda kind, payload: seen.append((kind, payload)))
        self.assertEqual(seen, [("text", "hello")])
        candidates.assert_not_called()


if __name__ == "__main__":
    unittest.main()
