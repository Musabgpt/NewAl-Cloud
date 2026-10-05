"""Free-only provider failover for MusabAI.

The currently selected model is tried first.  If it fails before emitting any
stream event, MusabAI walks the canonical free pool:

Groq -> Gemini -> OpenRouter Free -> NVIDIA.

Providers without credentials are skipped. Retryable failures use one short
retry, then a circuit-breaker cooldown so a busy provider is not hammered.
A fallback never starts after visible streaming output has begun, preventing
duplicate text/tool events in the chat.
"""
import os
import random
import threading
import time

from . import providers, settings

FREE_POOL = [
    {
        "id": "groq/gpt-oss-120b-free",
        "name": "Groq Free",
        "base_url": "https://api.groq.com/openai/v1",
        "model": "openai/gpt-oss-120b",
        "provider": "openai",
        "api_key_envs": ["GROQ_API_KEY"],
        "free": True,
    },
    {
        "id": "gemini/3.7-flash-free",
        "name": "Google Gemini Free",
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
        "model": "gemini-3.7-flash",
        "provider": "openai",
        "api_key_envs": ["GEMINI_API_KEY", "GOOGLE_API_KEY"],
        "free": True,
    },
    {
        "id": "openrouter/free",
        "name": "OpenRouter Free",
        "base_url": "https://openrouter.ai/api/v1",
        "model": "openrouter/free",
        "provider": "openai",
        "api_key_envs": ["OPENROUTER_API_KEY"],
        "free": True,
    },
    {
        "id": "nvidia/nemotron-3-ultra-free",
        "name": "NVIDIA Free Endpoint",
        "base_url": "https://integrate.api.nvidia.com/v1",
        "model": "nvidia/nemotron-3-ultra-550b-a55b",
        "provider": "openai",
        "api_key_envs": ["NVIDIA_API_KEY", "NVAPI_KEY"],
        "free": True,
    },
]

_RETRYABLE = {429, 500, 502, 503, 504}
_HEALTH = {}
_LOCK = threading.RLock()


def _now():
    return time.monotonic()


def _provider_id(spec):
    return str((spec or {}).get("id") or (spec or {}).get("model") or (spec or {}).get("base_url") or "unknown")


def _base(spec):
    return str((spec or {}).get("base_url") or "").rstrip("/")


def _key(spec):
    value = str(spec.get("api_key") or "")
    if value:
        return value
    names = spec.get("api_key_envs") or ([spec.get("api_key_env")] if spec.get("api_key_env") else [])
    for name in names:
        if name and os.environ.get(name):
            return os.environ[name]
    return ""


def _explicitly_free(spec):
    if spec.get("free") is True:
        return True
    mid = str(spec.get("id") or "").lower()
    model = str(spec.get("model") or "").lower()
    return mid.endswith("/free") or model.endswith(":free") or model == "openrouter/free"


def _state(pid):
    with _LOCK:
        return dict(_HEALTH.get(pid) or {})


def _available(spec):
    state = _state(_provider_id(spec))
    return float(state.get("cooldown_until") or 0) <= _now()


def _mark_success(spec, latency):
    pid = _provider_id(spec)
    with _LOCK:
        _HEALTH[pid] = {
            "state": "available",
            "failures": 0,
            "cooldown_until": 0.0,
            "last_error": "",
            "latency_ms": int(max(0.0, latency) * 1000),
            "updated_at": time.time(),
        }


def _status(error):
    return int(getattr(error, "status", 0) or 0)


def _retryable(error):
    if isinstance(error, (TimeoutError, OSError)):
        return True
    status = _status(error)
    if status in _RETRYABLE:
        return True
    text = str(error).lower()
    return any(word in text for word in (
        "overload", "temporarily unavailable", "service unavailable", "timeout",
        "timed out", "rate limit", "too many requests", "connection reset",
        "cannot reach", "connection refused",
    ))


def _cooldown_seconds(error, failures):
    status = _status(error)
    if failures >= 3:
        return 120
    if status == 429 or "rate limit" in str(error).lower():
        return 30
    if status in {502, 503, 504} or "overload" in str(error).lower():
        return 60
    if status in {401, 403}:
        return 300
    if status == 400:
        return 180
    return 20


def _mark_failure(spec, error):
    pid = _provider_id(spec)
    with _LOCK:
        old = _HEALTH.get(pid) or {}
        failures = int(old.get("failures") or 0) + 1
        wait = _cooldown_seconds(error, failures)
        status = _status(error)
        if status in {401, 403}:
            state = "auth_error"
        elif status == 429:
            state = "rate_limited"
        elif status in {500, 502, 503, 504} or "overload" in str(error).lower():
            state = "overloaded"
        else:
            state = "cooldown"
        _HEALTH[pid] = {
            "state": state,
            "failures": failures,
            "cooldown_until": _now() + wait,
            "last_error": str(error)[:500],
            "status": status,
            "updated_at": time.time(),
        }


def health_snapshot():
    """Small diagnostics object for UI/tests; never contains credentials."""
    now = _now()
    with _LOCK:
        return {
            pid: dict(value, cooling_down=float(value.get("cooldown_until") or 0) > now)
            for pid, value in _HEALTH.items()
        }


def reset_health():
    """Tests and explicit reconnect actions can clear the in-process breaker."""
    with _LOCK:
        _HEALTH.clear()


def candidates(current):
    """Return configured, credentialed, free fallbacks in canonical order."""
    current_spec = getattr(current, "spec", {}) or {}
    seen_ids = {_provider_id(current_spec)}
    seen_bases = {_base(current_spec)} if _base(current_spec) else set()

    # Canonical pool first. User-added fallbacks are accepted only when they
    # explicitly declare themselves free, so a fallback can never silently bill.
    configured = settings.user().get("fallback_models") or []
    values = list(FREE_POOL) + [x for x in configured if isinstance(x, dict) and _explicitly_free(x)]

    out = []
    for raw in values:
        spec = dict(raw)
        mid = _provider_id(spec)
        base = _base(spec)
        if not mid or mid in seen_ids or not base or base in seen_bases:
            continue
        key = _key(spec)
        if (spec.get("api_key_env") or spec.get("api_key_envs")) and not key:
            continue
        if not _explicitly_free(spec) or not _available(spec):
            continue
        spec["api_key"] = key
        seen_ids.add(mid)
        seen_bases.add(base)
        out.append(spec)
    return out


def provider(spec):
    if spec.get("provider") == "anthropic":
        return providers.Anthropic(spec.get("api_key", ""), spec.get("base_url") or "https://api.anthropic.com")
    return providers.OpenAICompat(spec["base_url"], spec.get("api_key", ""), spec.get("headers"))


class _ObservedEvents:
    """Tracks whether an attempt has emitted anything visible to the UI."""
    def __init__(self, callback):
        self.callback = callback
        self.emitted = False

    def __call__(self, kind, payload):
        self.emitted = True
        if self.callback:
            self.callback(kind, payload)


def _attempt(client_provider, model, messages, tools, kwargs):
    call_kwargs = dict(kwargs)
    observed = _ObservedEvents(call_kwargs.get("on_event"))
    if "on_event" in call_kwargs:
        call_kwargs["on_event"] = observed
    started = _now()
    try:
        result = client_provider.chat(model, messages, tools=tools, **call_kwargs)
        return result, observed.emitted, _now() - started
    except Exception as error:
        setattr(error, "_musab_emitted", observed.emitted)
        raise


def _call_with_retry(spec, client_provider, model, messages, tools, kwargs):
    attempts = 2
    last = None
    for attempt in range(attempts):
        started = _now()
        try:
            result, emitted, latency = _attempt(client_provider, model, messages, tools, kwargs)
            _mark_success(spec, latency)
            return result
        except (providers.ProviderError, TimeoutError, OSError) as error:
            last = error
            # Once the UI has received stream output, switching providers would
            # duplicate or contradict text/tool calls. Surface that failure.
            if getattr(error, "_musab_emitted", False):
                _mark_failure(spec, error)
                raise
            if not _retryable(error) or attempt + 1 >= attempts:
                _mark_failure(spec, error)
                raise
            # Short jittered retry. We intentionally fail over quickly rather
            # than making the user wait through long exponential backoff.
            delay = min(1.5, 0.25 * (2 ** attempt) + random.random() * 0.15)
            time.sleep(delay)
    raise last


def chat(client, messages, tools=None, **kwargs):
    current_spec = dict(getattr(client, "spec", {}) or {})
    current_spec.setdefault("id", getattr(client, "model_name", "current"))
    current_spec.setdefault("model", getattr(client, "model_name", "current"))
    old_id = _provider_id(current_spec)
    errors = []

    if _available(current_spec):
        try:
            return _call_with_retry(current_spec, client.provider, client.model_name, messages, tools, kwargs)
        except (providers.ProviderError, TimeoutError, OSError) as first:
            # Do not fall back after any visible stream event.
            if getattr(first, "_musab_emitted", False):
                raise
            errors.append(old_id + ": " + str(first))
    else:
        errors.append(old_id + ": provider is cooling down")

    for spec in candidates(client):
        next_provider = provider(spec)
        try:
            result = _call_with_retry(spec, next_provider, spec.get("model") or spec["id"], messages, tools, kwargs)
            client.provider = next_provider
            client.model_name = spec.get("model") or spec["id"]
            client.spec = spec
            client._last_fallback = {
                "from": old_id,
                "to": spec["id"],
                "error": errors[-1] if errors else "",
            }
            return result
        except (providers.ProviderError, TimeoutError, OSError) as error:
            if getattr(error, "_musab_emitted", False):
                raise
            errors.append(spec["id"] + ": " + str(error))

    message = "Free AI providers are temporarily unavailable"
    if errors:
        message += ": " + " | ".join(errors)[:1400]
    raise providers.ProviderError(message)
