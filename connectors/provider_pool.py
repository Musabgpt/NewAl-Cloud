"""Failover for real OpenAI-compatible providers; unavailable credentials are skipped."""
import os
from . import providers, settings

FREE_POOL = [
    {"id": "kilo-auto/free", "name": "Kilo Auto Free", "base_url": "https://api.kilo.ai/api/gateway", "model": "kilo-auto/free", "provider": "openai"},
    {"id": "openrouter/llama-free", "name": "OpenRouter Free", "base_url": "https://openrouter.ai/api/v1", "model": "meta-llama/llama-3.3-70b-instruct:free", "provider": "openai", "api_key_env": "OPENROUTER_API_KEY"},
    {"id": "groq/llama-free", "name": "Groq Free Tier", "base_url": "https://api.groq.com/openai/v1", "model": "llama-3.3-70b-versatile", "provider": "openai", "api_key_env": "GROQ_API_KEY"},
    {"id": "cerebras/llama-free", "name": "Cerebras Free Tier", "base_url": "https://api.cerebras.ai/v1", "model": "llama-3.3-70b", "provider": "openai", "api_key_env": "CEREBRAS_API_KEY"},
    {"id": "gemini/flash-free", "name": "Google Gemini Free Tier", "base_url": "https://generativelanguage.googleapis.com/v1beta/openai", "model": "gemini-2.0-flash", "provider": "openai", "api_key_env": "GEMINI_API_KEY"},
    {"id": "huggingface/auto-free", "name": "Hugging Face Inference", "base_url": "https://router.huggingface.co/v1", "model": "meta-llama/Llama-3.1-8B-Instruct", "provider": "openai", "api_key_env": "HF_TOKEN"},
]


def candidates(current):
    configured = settings.user().get("fallback_models") or []
    values = list(configured) + FREE_POOL
    out, seen = [], {current.spec.get("id")}
    for raw in values:
        spec = dict(raw) if isinstance(raw, dict) else {}
        mid = spec.get("id")
        if not mid or mid in seen or not spec.get("base_url"):
            continue
        key = spec.get("api_key") or os.environ.get(spec.get("api_key_env", ""), "")
        if spec.get("api_key_env") and not key:
            continue
        spec["api_key"] = key
        seen.add(mid); out.append(spec)
    return out


def provider(spec):
    if spec.get("provider") == "anthropic":
        return providers.Anthropic(spec.get("api_key", ""), spec.get("base_url") or "https://api.anthropic.com")
    return providers.OpenAICompat(spec["base_url"], spec.get("api_key", ""), spec.get("headers"))


def chat(client, messages, tools=None, **kwargs):
    old_id = getattr(client, "id", getattr(client, "model_name", "unknown"))
    try:
        return client.provider.chat(client.model_name, messages, tools=tools, **kwargs)
    except (providers.ProviderError, TimeoutError, OSError) as first:
        errors = [str(first)]
        for spec in candidates(client):
            try:
                next_provider = provider(spec)
                result = next_provider.chat(spec.get("model") or spec["id"], messages, tools=tools, **kwargs)
                client.provider = next_provider
                client.model_name = spec.get("model") or spec["id"]
                client.spec = spec
                client._last_fallback = {"from": old_id, "to": spec["id"], "error": errors[-1]}
                return result
            except (providers.ProviderError, TimeoutError, OSError) as error:
                errors.append(spec["id"] + ": " + str(error))
        raise providers.ProviderError("all configured model providers failed: " + " | ".join(errors)[:1600]) from first

