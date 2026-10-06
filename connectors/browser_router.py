"""Deterministic browser tool selector for MusabAI.

Routing policy mirrors the project architecture:
API -> service-specific MCP -> Playwright MCP -> Browser Use -> open-browser-use.

open-browser-use may be selected earlier only when the task explicitly requires the
user's already-signed-in browser session. The selector never invents availability:
every route is derived from a live connected account or a persisted, handshaken MCP
server in the current project.
"""
import json
import re
from urllib.parse import urlsplit

from . import connectors, mcp_config, tools

NAMES = ["browser_route"]

_BROWSER_BUNDLES = ("playwright", "browser-use", "open-browser-use")
_API_PROVIDERS = {
    "github": ("github.com", "api.github.com"),
    "gitlab": ("gitlab.com",),
    "drive": ("drive.google.com",),
    "gmail": ("mail.google.com", "gmail.com"),
    "calendar": ("calendar.google.com",),
    "docs": ("docs.google.com",),
    "sheets": ("sheets.google.com",),
    "notion": ("notion.so", "notion.com"),
    "figma": ("figma.com",),
}


def _norm(value):
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())


def _host(target):
    value = str(target or "").strip()
    if "://" not in value and "." in value:
        value = "https://" + value
    try:
        return (urlsplit(value).hostname or "").lower()
    except ValueError:
        return ""


def _connected_accounts():
    try:
        rows = connectors.status().get("connectors") or []
    except Exception:
        return {}
    return {
        str(row.get("id")): row
        for row in rows
        if isinstance(row, dict) and row.get("status") == "connected"
    }


def _saved_mcp(root):
    try:
        return mcp_config.read(root)
    except (OSError, ValueError, TypeError):
        return {}


def capabilities(root):
    accounts = _connected_accounts()
    servers = _saved_mcp(root)
    bundles = {
        name: record for name, record in servers.items()
        if isinstance(record, dict) and record.get("bundle") in _BROWSER_BUNDLES
    }
    custom = {
        name: record for name, record in servers.items()
        if isinstance(record, dict) and not record.get("bundle")
    }
    return {
        "connected_apis": sorted(
            provider for provider in accounts
            if provider in _API_PROVIDERS
        ),
        "connected_mcp_accounts": sorted(
            provider for provider in accounts
            if provider in connectors.MCP_PROVIDERS
        ),
        "browser_bundles": {
            bundle: {
                "enabled": bundle in bundles,
                "tools": int((bundles.get(bundle) or {}).get("tools") or 0),
            }
            for bundle in _BROWSER_BUNDLES
        },
        "custom_mcp": sorted(custom),
    }


def _api_match(service, target, available):
    service_key = _norm(service)
    host = _host(target)
    for provider in available:
        if service_key and service_key in {_norm(provider), _norm(connectors.CATALOG.get(provider, ""))}:
            return provider
        if host and any(host == d or host.endswith("." + d) for d in _API_PROVIDERS.get(provider, ())):
            return provider
    return ""


def _mcp_match(service, target, state):
    service_key = _norm(service)
    host = _host(target)
    candidates = list(state["connected_mcp_accounts"]) + list(state["custom_mcp"])
    for name in candidates:
        key = _norm(name)
        if service_key and (service_key == key or service_key in key or key in service_key):
            return name
        if host and key and key in _norm(host):
            return name
    return ""


def select(root, target="", service="", requires_existing_session=False,
           complex_ui=False, structured_ui=True):
    state = capabilities(root)
    api = _api_match(service, target, state["connected_apis"])
    if api:
        return {
            "route": "api",
            "provider": api,
            "reason": "A connected service API is available; use it before browser automation.",
            "available": True,
            "order": ["api", "mcp", "playwright", "browser-use", "open-browser-use"],
            "state": state,
        }

    service_mcp = _mcp_match(service, target, state)
    if service_mcp:
        return {
            "route": "mcp",
            "provider": service_mcp,
            "reason": "A connected service-specific MCP server is available.",
            "available": True,
            "order": ["api", "mcp", "playwright", "browser-use", "open-browser-use"],
            "state": state,
        }

    enabled = {
        key for key, value in state["browser_bundles"].items()
        if value.get("enabled") and value.get("tools", 0) > 0
    }

    # A real signed-in browser session is the one explicit exception to the generic
    # fallback sequence: open-browser-use exists specifically for that requirement.
    if requires_existing_session and "open-browser-use" in enabled:
        route = "open-browser-use"
        reason = "The task requires the user's existing signed-in Chromium session."
    elif "playwright" in enabled and (structured_ui or not complex_ui):
        route = "playwright"
        reason = "Playwright MCP is enabled and is preferred for structured DOM/accessibility workflows."
    elif "browser-use" in enabled:
        route = "browser-use"
        reason = "Browser Use MCP is enabled and is the fallback for a complex browser workflow."
    elif "playwright" in enabled:
        route = "playwright"
        reason = "Playwright MCP is the only verified browser MCP currently enabled."
    elif "open-browser-use" in enabled:
        route = "open-browser-use"
        reason = "open-browser-use is the only verified browser MCP currently enabled."
    else:
        return {
            "route": "unavailable",
            "available": False,
            "reason": "No verified browser MCP bundle is enabled for this project.",
            "setup_order": ["playwright", "browser-use", "open-browser-use"],
            "order": ["api", "mcp", "playwright", "browser-use", "open-browser-use"],
            "state": state,
        }

    return {
        "route": route,
        "available": True,
        "reason": reason,
        "tool_prefix": "mcp__" + route + "__",
        "order": ["api", "mcp", "playwright", "browser-use", "open-browser-use"],
        "state": state,
    }


@tools.tool(
    "browser_route",
    "Choose the safest available browser route from real connected capabilities. Order: API, service MCP, Playwright, Browser Use, open-browser-use. This tool only selects; it never performs browser actions.",
    {
        "target": {"type": "string", "description": "Website URL or host, if known"},
        "service": {"type": "string", "description": "Service name such as GitHub, Notion, or Figma, if known"},
        "requires_existing_session": {"type": "boolean", "description": "True only when the task needs the user's already signed-in browser session"},
        "complex_ui": {"type": "boolean", "description": "True for visual/dynamic workflows that structured DOM automation may not handle well"},
        "structured_ui": {"type": "boolean", "description": "True when the page exposes normal DOM/accessibility controls"},
    },
    [],
    "read",
)
def browser_route(ctx, target="", service="", requires_existing_session=False,
                  complex_ui=False, structured_ui=True):
    result = select(
        ctx.root,
        target=target,
        service=service,
        requires_existing_session=bool(requires_existing_session),
        complex_ui=bool(complex_ui),
        structured_ui=bool(structured_ui),
    )
    return json.dumps(result, ensure_ascii=False), {
        "route": result.get("route"),
        "available": result.get("available", False),
    }
