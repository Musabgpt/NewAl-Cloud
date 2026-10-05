"""Vetted MCP bundle catalog shipped with MusabAI.

Bundles are real server definitions, not fake connection cards. A bundle is
reported available only when its runtime (and required credential) exists.
Enabling performs an actual initialize + tools/list handshake before persisting
the server into the project's private MCP configuration.
"""
import os
import re
import shutil
import time

from . import mcp_config

PATHS = {
    "/api/mcp-bundles",
    "/api/mcp-bundles/enable",
    "/api/mcp-bundles/test",
    "/api/mcp-bundles/disable",
}

BUNDLES = [
    {
        "id": "playwright",
        "name": "Microsoft Playwright MCP",
        "repository": "https://github.com/microsoft/playwright-mcp",
        "runtimes": ["npx"],
        "command": "npx",
        "args": ["-y", "@playwright/mcp@latest"],
        "description": "Browser automation using Playwright accessibility snapshots.",
    },
    {
        "id": "github",
        "name": "GitHub MCP Server",
        "repository": "https://github.com/github/github-mcp-server",
        "runtimes": ["github-mcp-server"],
        "command": "github-mcp-server",
        "args": ["stdio"],
        "credential_env_any": ["GITHUB_PERSONAL_ACCESS_TOKEN", "GITHUB_TOKEN", "GH_TOKEN"],
        "env_alias": "GITHUB_PERSONAL_ACCESS_TOKEN",
        "description": "GitHub's official MCP server. Requires its binary and a GitHub token.",
        "native_fallback": "MusabAI's Android GitHub connector remains available when the MCP binary is absent.",
    },
    {
        "id": "filesystem",
        "name": "MCP Reference Filesystem",
        "repository": "https://github.com/modelcontextprotocol/servers",
        "runtimes": ["npx"],
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-filesystem", "{root}"],
        "description": "Sandboxed file tools restricted to the current project root.",
    },
    {
        "id": "android",
        "name": "Android MCP",
        "repository": "https://github.com/us-all/android-mcp-server",
        "runtimes": ["npx", "adb"],
        "command": "npx",
        "args": ["-y", "@us-all/android-mcp"],
        "env": {"ANDROID_MCP_ALLOW_WRITE": "true"},
        "description": "ADB diagnostics and Android automation. Requires npx and adb.",
        "native_fallback": "On the phone itself MusabAI's native Android bridge works over localhost without Wi-Fi or ADB.",
    },
    {
        "id": "memory",
        "name": "MCP Reference Memory",
        "repository": "https://github.com/modelcontextprotocol/servers",
        "runtimes": ["npx"],
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-memory"],
        "env": {"MEMORY_FILE_PATH": "{memory_file}"},
        "description": "Persistent project-scoped knowledge-graph memory.",
    },
]


def _item(bundle_id):
    for item in BUNDLES:
        if item["id"] == bundle_id:
            return item
    raise ValueError("Unknown MCP bundle")


def _credential(item):
    for name in item.get("credential_env_any") or []:
        value = os.environ.get(name)
        if value:
            return name, value
    return "", ""


def _missing(item):
    missing = [name for name in item.get("runtimes") or [] if shutil.which(name) is None]
    if item.get("credential_env_any") and not _credential(item)[1]:
        missing.append("credential")
    return missing


def _spec(item, root):
    root = os.path.realpath(root)
    memory_dir = os.path.join(root, ".newal")
    os.makedirs(memory_dir, exist_ok=True)
    replacements = {
        "{root}": root,
        "{memory_file}": os.path.join(memory_dir, "mcp-memory.jsonl"),
    }

    def expand(value):
        text = str(value)
        for old, new in replacements.items():
            text = text.replace(old, new)
        return text

    env = {str(k): expand(v) for k, v in (item.get("env") or {}).items()}
    env_name, env_value = _credential(item)
    if env_value:
        env[item.get("env_alias") or env_name] = env_value
    return {
        "command": item["command"],
        "args": [expand(x) for x in item.get("args") or []],
        "env": env,
    }


def catalog(root=None):
    enabled = {}
    if root:
        try:
            enabled = mcp_config.read(root)
        except OSError:
            enabled = {}
    result = []
    for item in BUNDLES:
        missing = _missing(item)
        record = enabled.get(item["id"]) or {}
        active = record.get("bundle") == item["id"]
        if active:
            status = "enabled"
        elif "credential" in missing:
            status = "credentials_missing"
        elif missing:
            status = "runtime_missing"
        else:
            status = "available"
        public = {
            k: v for k, v in item.items()
            if k not in {"command", "args", "env", "credential_env_any", "env_alias"}
        }
        public.update({
            "available": not missing,
            "status": status,
            "missing": missing,
            "enabled": active,
            "tools": int(record.get("tools") or 0) if active else 0,
            "tested_at": int(record.get("tested_at") or 0) if active else 0,
        })
        result.append(public)
    return result


def _session_root(handler, data):
    sid = data.get("session", "")
    if not isinstance(sid, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", sid):
        raise ValueError("Open a project conversation first")
    return handler.service.get(sid).root


def _test(item, root):
    missing = _missing(item)
    if missing:
        raise RuntimeError("Missing requirements: " + ", ".join(missing))
    server = mcp_config.StdioServer(item["id"], _spec(item, root), root)
    try:
        server.start(timeout=45)
        return len(server.tools)
    finally:
        server.stop()


def _save_enabled(item, root, tools):
    with mcp_config.LOCK:
        servers = mcp_config.read(root)
        existing = servers.get(item["id"])
        if existing and existing.get("bundle") not in (None, item["id"]):
            raise ValueError("An MCP server already uses this name")
        if existing and not existing.get("bundle"):
            raise ValueError("Remove the custom MCP server with this name first")
        servers[item["id"]] = {
            "spec": _spec(item, root),
            "tools": int(tools),
            "tested_at": int(time.time()),
            "bundle": item["id"],
        }
        mcp_config.save(root, servers)


def route(handler, method, path, body=None):
    if path not in PATHS:
        return False
    try:
        data = handler._query() if method == "GET" else (body or {})
        root = None
        sid = data.get("session", "")
        if sid:
            root = _session_root(handler, data)

        if method == "GET" and path == "/api/mcp-bundles":
            handler._json({
                "bundles": catalog(root),
                "automatic": True,
                "note": "Enabled bundles are discovered by the agent automatically. Availability is never faked.",
            })
            return True

        if method != "POST" or path == "/api/mcp-bundles":
            handler._json({"error": "Method not allowed"}, 405)
            return True

        root = _session_root(handler, data)
        item = _item(data.get("id"))

        if path.endswith("/disable"):
            with mcp_config.LOCK:
                servers = mcp_config.read(root)
                record = servers.get(item["id"])
                if not record or record.get("bundle") != item["id"]:
                    raise ValueError("Bundle is not enabled")
                del servers[item["id"]]
                mcp_config.save(root, servers)
            handler._json({"ok": True})
            return True

        count = _test(item, root)
        if path.endswith("/enable"):
            _save_enabled(item, root, count)
        handler._json({"ok": True, "tools": count, "enabled": path.endswith("/enable")})
    except (ValueError, KeyError, OSError, RuntimeError, TypeError) as error:
        message = str(error)
        if len(message) > 300:
            message = message[:300]
        handler._json({"error": "MCP bundle could not be activated: " + message}, 400)
    return True
