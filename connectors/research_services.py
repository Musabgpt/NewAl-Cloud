"""Optional self-hosted research stack for MusabAI.

SearXNG is used as the preferred metasearch backend when configured.
Crawl4AI is used only as a fallback when the built-in lightweight web fetch
cannot read a page. Service URLs are stored in the private app config; the
Crawl4AI bearer token lives in Android Keystore (or CRAWL4AI_API_TOKEN on
non-Android hosts). No service is reported ready until a real request succeeds.
"""
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from urllib.parse import urlsplit, urlunsplit

from . import phone, settings

PATHS = {
    "/api/research-services",
    "/api/research-services/save",
    "/api/research-services/remove",
    "/api/research-services/test",
}
MAX_RESPONSE = 4 * 1024 * 1024
TIMEOUT = 45


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


_OPENER = urllib.request.build_opener(_NoRedirect)


def _config():
    value = settings.user().get("research_services") or {}
    return value if isinstance(value, dict) else {}


def _save_config(value):
    settings.save({"research_services": value})


def _base(value):
    if not isinstance(value, str):
        raise ValueError("Enter a service URL")
    value = value.strip()
    if not value or len(value) > 2048:
        raise ValueError("Enter a service URL")
    parsed = urlsplit(value)
    loopback = parsed.hostname in {"127.0.0.1", "localhost", "::1"}
    if not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("Use a plain service base URL without credentials, query or fragment")
    if parsed.scheme != "https" and not (parsed.scheme == "http" and loopback):
        raise ValueError("Use HTTPS, or HTTP only on localhost")
    path = (parsed.path or "").rstrip("/")
    return urlunsplit((parsed.scheme.lower(), parsed.netloc, path, "", ""))


def _target(value):
    if not isinstance(value, str) or len(value) > 4096:
        raise ValueError("Invalid target URL")
    value = value.strip()
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("Only public http(s) target URLs are supported")
    return value


def _secret_status():
    if os.environ.get("CRAWL4AI_API_TOKEN"):
        return True
    if not phone.available():
        return False
    try:
        out = phone.call("research_secret_status", timeout=15, service="crawl4ai")
        return bool(out.get("ok") and out.get("configured"))
    except Exception:
        return False


def _secret():
    env = os.environ.get("CRAWL4AI_API_TOKEN", "").strip()
    if env:
        return env
    if not phone.available():
        return ""
    try:
        out = phone.call("research_secret_get", timeout=15, service="crawl4ai")
        return str(out.get("value") or "") if out.get("ok") else ""
    except Exception:
        return ""


def _set_secret(value):
    if not phone.available():
        raise RuntimeError("Secure Crawl4AI token storage requires the Android app; on desktop use CRAWL4AI_API_TOKEN")
    out = phone.call("research_secret_set", timeout=15, service="crawl4ai", value=value)
    if not out.get("ok"):
        raise RuntimeError("Could not save Crawl4AI credential securely")


def _remove_secret():
    if not phone.available():
        return
    try:
        phone.call("research_secret_remove", timeout=15, service="crawl4ai")
    except Exception:
        pass


def _request(url, method="GET", body=None, token="", timeout=TIMEOUT):
    headers = {
        "Accept": "application/json",
        "User-Agent": "MusabAI-Research/1",
    }
    data = None
    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = "Bearer " + token
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with _OPENER.open(req, timeout=timeout) as response:
            raw = response.read(MAX_RESPONSE + 1)
            if len(raw) > MAX_RESPONSE:
                raise RuntimeError("Research service response exceeded the size limit")
            ctype = response.headers.get("Content-Type", "")
            if "json" not in ctype.lower() and not raw.lstrip().startswith((b"{", b"[")):
                raise RuntimeError("Research service did not return JSON")
            return json.loads(raw.decode("utf-8", "replace"))
    except urllib.error.HTTPError as exc:
        raise RuntimeError("Research service returned HTTP %s" % exc.code) from None
    except (urllib.error.URLError, TimeoutError, OSError, ValueError, json.JSONDecodeError) as exc:
        raise RuntimeError("Research service request failed") from None


def searxng_search(query, n=6):
    """Return search rows, or None when SearXNG is not configured/usable."""
    cfg = _config()
    base = cfg.get("searxng_url", "")
    if not base or not cfg.get("searxng_tested_at"):
        return None
    try:
        params = urllib.parse.urlencode({"q": str(query), "format": "json"})
        data = _request(base + "/search?" + params, timeout=20)
        rows = data.get("results")
        if not isinstance(rows, list):
            return None
        out = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            url = str(row.get("url") or "").strip()
            if not re.match(r"^https?://", url):
                continue
            out.append({
                "title": str(row.get("title") or url),
                "url": url,
                "snippet": str(row.get("content") or row.get("snippet") or ""),
            })
            if len(out) >= max(1, min(int(n or 6), 20)):
                break
        return out or None
    except Exception:
        return None


def crawl4ai_fetch(url, _allow_unverified=False):
    """Return extracted markdown, or None when Crawl4AI is not verified/usable."""
    cfg = _config()
    base = cfg.get("crawl4ai_url", "")
    if not base or (not _allow_unverified and not cfg.get("crawl4ai_tested_at")):
        return None
    token = _secret()
    try:
        data = _request(
            base + "/crawl",
            method="POST",
            token=token,
            body={
                "urls": [_target(url)],
                "browser_config": {},
                "crawler_config": {"stream": False},
            },
            timeout=60,
        )
        if isinstance(data.get("result"), dict):
            data = data["result"]
        rows = data.get("results") if isinstance(data, dict) else None
        if not isinstance(rows, list) or not rows:
            return None
        row = rows[0] if isinstance(rows[0], dict) else {}
        if row.get("success") is False:
            return None
        markdown = row.get("markdown")
        if isinstance(markdown, dict):
            markdown = (markdown.get("raw_markdown") or markdown.get("fit_markdown")
                        or markdown.get("markdown") or "")
        text = str(markdown or row.get("cleaned_html") or row.get("html") or "").strip()
        return text or None
    except Exception:
        return None


def public_status():
    cfg = _config()
    return {
        "searxng": {
            "url": cfg.get("searxng_url", ""),
            "configured": bool(cfg.get("searxng_url")),
            "tested_at": int(cfg.get("searxng_tested_at") or 0),
        },
        "crawl4ai": {
            "url": cfg.get("crawl4ai_url", ""),
            "configured": bool(cfg.get("crawl4ai_url")),
            "token_configured": _secret_status(),
            "tested_at": int(cfg.get("crawl4ai_tested_at") or 0),
        },
        "routing": {
            "search": ["searxng", "bing-rss", "duckduckgo", "wikipedia"],
            "fetch": ["direct-http", "crawl4ai", "browser-route"],
        },
    }


def _test_service(service):
    cfg = _config()
    if service == "searxng":
        base = cfg.get("searxng_url", "")
        if not base:
            raise ValueError("Save a SearXNG URL first")
        params = urllib.parse.urlencode({"q": "MusabAI", "format": "json"})
        data = _request(base + "/search?" + params, timeout=20)
        if not isinstance(data.get("results"), list):
            raise RuntimeError("SearXNG JSON search is not enabled")
        return {"ok": True, "service": service, "results": len(data["results"])}
    if service == "crawl4ai":
        base = cfg.get("crawl4ai_url", "")
        if not base:
            raise ValueError("Save a Crawl4AI URL first")
        health = _request(base + "/health", timeout=15)
        if not isinstance(health, dict):
            raise RuntimeError("Crawl4AI health check failed")
        text = crawl4ai_fetch("https://example.com", _allow_unverified=True)
        if not text:
            raise RuntimeError("Crawl4AI could not complete a test crawl")
        return {"ok": True, "service": service, "chars": len(text)}
    raise ValueError("Unknown research service")


def route(handler, method, path, body=None):
    if path not in PATHS:
        return False
    try:
        if method == "GET" and path == "/api/research-services":
            handler._json(public_status())
            return True
        if method != "POST" or path == "/api/research-services":
            handler._json({"error": "Method not allowed"}, 405)
            return True

        data = body or {}
        service = data.get("service", "")
        if service not in {"searxng", "crawl4ai"}:
            raise ValueError("Unknown research service")

        cfg = _config()
        key = service + "_url"
        if path.endswith("/save"):
            cfg[key] = _base(data.get("url", ""))
            cfg.pop(service + "_tested_at", None)
            if service == "crawl4ai":
                token = data.get("token")
                if token is not None and str(token).strip():
                    value = str(token).strip()
                    if len(value) < 8 or len(value) > 8192 or re.search(r"\s", value):
                        raise ValueError("Invalid Crawl4AI token")
                    _set_secret(value)
            _save_config(cfg)
            handler._json({"ok": True, "configured": True})
            return True

        if path.endswith("/remove"):
            cfg.pop(key, None)
            cfg.pop(service + "_tested_at", None)
            _save_config(cfg)
            if service == "crawl4ai":
                _remove_secret()
            handler._json({"ok": True, "configured": False})
            return True

        if path.endswith("/test"):
            result = _test_service(service)
            cfg = _config()
            cfg[service + "_tested_at"] = int(time.time())
            _save_config(cfg)
            result["tested_at"] = cfg[service + "_tested_at"]
            handler._json(result)
            return True
    except (ValueError, RuntimeError, OSError, phone.PhoneError):
        try:
            data = body or {}
            service = data.get("service", "")
            if path.endswith("/test") and service in {"searxng", "crawl4ai"}:
                cfg = _config()
                if cfg.pop(service + "_tested_at", None) is not None:
                    _save_config(cfg)
        except Exception:
            pass
        handler._json({"error": "Research service configuration or live test failed"}, 400)
    return True
