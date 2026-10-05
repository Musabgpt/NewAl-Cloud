"""Android-Keystore-backed credentials for MusabAI's free provider pool.

The browser can save/remove/test a key but never read it back. On Android the
value is persisted by ConnectorVault and fetched only by the embedded Python
engine over the authenticated 127.0.0.1 phone bridge.
"""
import re

from . import phone, provider_pool, providers

PATHS = {
    "/api/free-providers",
    "/api/free-providers/save",
    "/api/free-providers/remove",
    "/api/free-providers/test",
}

PUBLIC = [
    ("groq", "Groq Free"),
    ("gemini", "Google Gemini Free"),
    ("openrouter", "OpenRouter Free"),
    ("nvidia", "NVIDIA Free"),
]


def _provider(name):
    if name not in {x[0] for x in PUBLIC}:
        raise ValueError("Unknown free AI provider")
    return name


def _phone(action, provider, **extra):
    result = phone.call(action, timeout=30, provider=provider, **extra)
    if not result.get("ok", False):
        raise RuntimeError(result.get("error") or "Android secure storage request failed")
    return result


def secret(provider):
    """Return one secret to provider_pool; never exposed by an HTTP GET route."""
    provider = _provider(provider)
    return str(_phone("provider_secret_get", provider).get("value") or "")


def configured(provider):
    try:
        return bool(_phone("provider_secret_status", _provider(provider)).get("configured"))
    except (phone.PhoneError, RuntimeError, OSError):
        return False


def _spec(provider):
    for spec in provider_pool.FREE_POOL:
        if spec.get("secret_id") == provider:
            item = dict(spec)
            item["api_key"] = secret(provider)
            return item
    raise ValueError("Provider is not in the free pool")


def _test(provider):
    spec = _spec(provider)
    client = provider_pool.provider(spec)
    # A one-token real request proves endpoint + credential, not just that a
    # string was saved. It uses only the user's explicitly configured free tier.
    client.chat(
        spec["model"],
        [{"role": "user", "content": "Reply with OK."}],
        tools=[],
        max_tokens=1,
        temperature=0,
        reasoning="off",
    )
    return True


def route(handler, method, path, body=None):
    if path not in PATHS:
        return False
    try:
        if method == "GET" and path == "/api/free-providers":
            items = []
            for pid, name in PUBLIC:
                items.append({"id": pid, "name": name, "configured": configured(pid)})
            handler._json({"providers": items, "free_only": True})
            return True

        if method != "POST" or path == "/api/free-providers":
            handler._json({"error": "Method not allowed"}, 405)
            return True

        data = body or {}
        pid = _provider(data.get("provider", ""))
        if path.endswith("/save"):
            value = data.get("key", "")
            if not isinstance(value, str):
                raise ValueError("Invalid API key")
            value = value.strip()
            if len(value) < 8 or len(value) > 8192 or re.search(r"\s", value):
                raise ValueError("Invalid API key")
            _phone("provider_secret_set", pid, value=value)
            handler._json({"ok": True, "configured": True})
            return True
        if path.endswith("/remove"):
            _phone("provider_secret_remove", pid)
            handler._json({"ok": True, "configured": False})
            return True
        if path.endswith("/test"):
            _test(pid)
            handler._json({"ok": True, "connected": True})
            return True
    except (ValueError, RuntimeError, phone.PhoneError, providers.ProviderError, OSError) as error:
        # Never echo response bodies: some providers include request metadata.
        status = getattr(error, "status", 0)
        suffix = " (HTTP %s)" % status if status else ""
        handler._json({"error": "Free provider test/configuration failed" + suffix}, 400)
    return True
