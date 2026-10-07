"""Vetted MCP bundle catalog shipped with MusabAI.

Bundles are real server definitions, not fake connection cards. A bundle is
reported available only when its runtime (and required credential) exists.
Enabling performs an actual initialize + tools/list handshake before persisting
the server into the project's private MCP configuration.
"""
import hashlib
import os
import re
import shutil
import time

from . import mcp_config, runtime_manager

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
        "args": ["-y", "@playwright/mcp@0.0.83", "--isolated"],
        "description": "Structured browser automation using Playwright accessibility snapshots. The vetted bundle pins the reviewed MCP package version and uses isolated browser state.",
        "browser_role": "structured",
    },
    {
        "id": "browser-use",
        "name": "Browser Use MCP",
        "repository": "https://github.com/browser-use/browser-use",
        "runtimes": ["uvx"],
        "command": "uvx",
        "args": ["browser-use==0.13.5", "--cli-mcp"],
        "description": "Browser Use CLI MCP for complex or visually difficult pages. Uses the package/stdio contract published in its official server.json.",
        "browser_role": "complex",
        "manual_setup": "Install uv/uvx and a supported local browser runtime before enabling this bundle.",
    },
    {
        "id": "open-browser-use",
        "name": "open-browser-use",
        "repository": "https://github.com/open-browser-use/open-browser-use",
        "runtimes": ["obu"],
        "command": "obu",
        "args": ["mcp", "stdio"],
        "description": "Controls an existing real Chromium session through the open-browser-use MCP server; useful when the task requires the user's logged-in session.",
        "browser_role": "existing_session",
        "manual_setup": "Install and verify open-browser-use first; its browser extension/native host has a user-visible setup boundary.",
    },
    {
        "id": "docling",
        "name": "Docling MCP",
        "repository": "https://github.com/docling-project/docling-mcp",
        "runtimes": ["uvx"],
        "command": "uvx",
        "args": ["--from", "docling-mcp[local]==3.3.0", "docling-mcp-server", "--transport", "stdio"],
        "env": {
            "DOCLING_MCP_CONVERSION_MODE": "local",
            "DOCLING_MCP_KEEP_IMAGES": "false",
        },
        "description": "Docling document understanding for PDF, Office, OCR, tables and structured conversion. The reviewed bundle pins Docling MCP 3.3.0 and starts its official stdio server in local mode.",
        "document_role": "structured",
        "manual_setup": "Requires uv/uvx. Local Docling is substantially larger than the built-in document reader and is downloaded only when you explicitly test/enable this bundle.",
        "native_fallback": "MusabAI's built-in document tools remain available for Markdown, text, HTML, ordinary PDF text and ZIP files.",
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
        "name": "Android MCP (external ADB, optional)",
        "repository": "https://github.com/us-all/android-mcp-server",
        "runtimes": ["npx", "adb"],
        "command": "npx",
        "args": ["-y", "@us-all/android-mcp"],
        "env": {"ANDROID_MCP_ALLOW_WRITE": "true"},
        "description": "Optional third-party ADB MCP for external-device diagnostics. This is not MusabAI's native on-phone bridge and it requires npx plus adb.",
        "native_fallback": "MusabAI Android Native Bridge is separate and works locally without adb, Wireless ADB, Wi-Fi pairing or USB ADB.",
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


def _runtime_requirements(item):
    return runtime_manager.requirements(item.get("runtimes") or [])


def _missing(item):
    state = _runtime_requirements(item)
    missing = list(state["missing"])
    if item.get("credential_env_any") and not _credential(item)[1]:
        missing.append("credential")
    return missing


def _spec(item, root):
    root = os.path.realpath(root)
    runtime = _runtime_requirements(item)
    memory_dir = os.path.join(root, ".newal")
    if runtime["runtime"] == runtime_manager.TERMUX and item.get("id") == "memory":
        project_key = hashlib.sha256(root.encode("utf-8")).hexdigest()[:20]
        memory_file = os.path.join(
            runtime_manager.termux_home(),
            ".musabai-mcp-memory-" + project_key + ".jsonl",
        )
    else:
        os.makedirs(memory_dir, exist_ok=True)
        memory_file = os.path.join(memory_dir, "mcp-memory.jsonl")
    replacements = {
        "{root}": root,
        "{memory_file}": memory_file,
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
        runtime = _runtime_requirements(item)
        missing = list(runtime["missing"])
        credential_missing = bool(item.get("credential_env_any") and not _credential(item)[1])
        record = enabled.get(item["id"]) or {}
        active = record.get("bundle") == item["id"]
        verified = bool(active and int(record.get("tested_at") or 0) > 0 and int(record.get("tools") or 0) > 0)
        if verified:
            status = "verified"
        elif credential_missing:
            status = "credentials_missing"
        elif runtime["unknown"]:
            status = "runtime_unavailable"
        elif missing:
            status = "runtime_missing"
        elif runtime["runtime"] == runtime_manager.TERMUX and not runtime["stdio"]:
            status = "bridge_required"
        elif runtime["runtime"] == runtime_manager.TERMUX and item["id"] == "filesystem":
            status = "needs_shared_path"
        else:
            status = "available"
        public = {
            k: v for k, v in item.items()
            if k not in {"command", "args", "env", "credential_env_any", "env_alias"}
        }
        public.update({
            "available": status == "available",
            "status": status,
            "missing": missing,
            "runtime": runtime["runtime"],
            "runtime_reason": runtime["reason"],
            "dependencies": list(item.get("runtimes") or []),
            "install_method": "on_demand" if item.get("command") in {"npx", "uvx"} else "manual_or_preinstalled",
            "start_method": "runtime_process_start(stdio=true)",
            "stop_method": "runtime_process_stop",
            "health_check": "MCP initialize + tools/list",
            "verified": verified,
            "installed": verified,
            "connected": False,
            "enabled": verified,
            "tools": int(record.get("tools") or 0) if verified else 0,
            "tested_at": int(record.get("tested_at") or 0) if verified else 0,
        })
        result.append(public)
    return result


def _session_root(handler, data):
    sid = data.get("session", "")
    if not isinstance(sid, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", sid):
        raise ValueError("Open a project conversation first")
    return handler.service.get(sid).root


def _test(item, root):
    runtime = _runtime_requirements(item)
    if runtime["unknown"]:
        raise RuntimeError(runtime["reason"])
    if runtime["missing"]:
        raise RuntimeError("Missing requirements: " + ", ".join(runtime["missing"]))
    if runtime["runtime"] == runtime_manager.TERMUX and item["id"] == "filesystem":
        raise RuntimeError(
            "Filesystem MCP cannot access MusabAI app-private project files from Termux. "
            "Use MusabAI built-in file tools until a shared project path is configured."
        )
    if runtime["runtime"] == runtime_manager.TERMUX and not runtime["stdio"]:
        raise RuntimeError(
            "Termux runtime is verified, but persistent MCP stdio transport is not active yet; "
            "use the Phase 6 localhost bridge before enabling this bundle."
        )
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
                "note": "Installed means a real initialize + tools/list handshake succeeded. Connected is never claimed from saved state alone.",
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
