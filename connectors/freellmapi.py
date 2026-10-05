"""Control the self-hosted FreeLLMAPI router on the same Android phone.

The Node server runs inside Termux on 127.0.0.1:3001. MusabAI talks only to
localhost; FreeLLMAPI handles provider/model routing, free-tier quotas,
cooldowns, sticky sessions and failover.
"""
from . import phone

PATHS = {
    "/api/freellmapi",
    "/api/freellmapi/setup",
    "/api/freellmapi/update",
    "/api/freellmapi/start",
    "/api/freellmapi/stop",
}

_ACTIONS = {
    "/api/freellmapi/setup": "freellmapi_setup",
    "/api/freellmapi/update": "freellmapi_update",
    "/api/freellmapi/start": "freellmapi_start",
    "/api/freellmapi/stop": "freellmapi_stop",
}


def _call(action):
    result = phone.call(action, timeout=30)
    if not result.get("ok", False):
        raise RuntimeError(result.get("error") or "FreeLLMAPI phone action failed")
    return result


def route(handler, method, path, body=None):
    if path not in PATHS:
        return False
    try:
        if method == "GET" and path == "/api/freellmapi":
            handler._json(_call("freellmapi_status"))
            return True
        if method == "POST" and path in _ACTIONS:
            handler._json(_call(_ACTIONS[path]))
            return True
        handler._json({"error": "Method not allowed"}, 405)
    except (phone.PhoneError, RuntimeError, OSError) as error:
        handler._json({"error": str(error)[:300]}, 400)
    return True
