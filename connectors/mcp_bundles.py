"""Vetted MCP bundle catalog shipped with MusabAI.

Bundles are real server definitions, not fake connection cards. A bundle is
reported available only when its runtime (and required credential) exists.
Enabling performs an actual initialize + tools/list handshake before persisting
the server into the project's private MCP configuration. Phase 8 keeps verified
installation separate from the live start/stop/reconnect process state.
"""
import hashlib
import json
import os
import re
import shutil
import tempfile
import threading
import time

from . import mcp_config, runtime_manager, tools

PATHS = {
    "/api/mcp-bundles",
    "/api/mcp-bundles/enable",
    "/api/mcp-bundles/test",
    "/api/mcp-bundles/disable",
    "/api/mcp-bundles/start",
    "/api/mcp-bundles/stop",
    "/api/mcp-bundles/reconnect",
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


_RUNNING_LOCK = threading.RLock()
_RUNNING = {}
_LAST_ERRORS = {}


def _runtime_state_path(root):
    path = mcp_config.path_for(root)
    return path.with_name(path.stem + ".runtime.json")


def _read_runtime_state(root):
    try:
        data = json.loads(_runtime_state_path(root).read_text())
        return data if isinstance(data, dict) else {}
    except (FileNotFoundError, ValueError, OSError):
        return {}


def _save_runtime_state(root, data):
    path = _runtime_state_path(root)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".mcp-runtime-")
    try:
        with os.fdopen(fd, "w") as stream:
            json.dump(data, stream, ensure_ascii=False)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def _key(root, bundle_id):
    return (os.path.realpath(root), bundle_id)


def _remember_process(root, item, server):
    process_id = str(getattr(server, "_termux_process_id", "") or "")
    if not process_id:
        return
    state = _read_runtime_state(root)
    state[item["id"]] = {
        "process_id": process_id,
        "started_at": int(time.time()),
    }
    _save_runtime_state(root, state)


def _forget_process(root, item):
    state = _read_runtime_state(root)
    if item["id"] in state:
        del state[item["id"]]
        _save_runtime_state(root, state)


def _attached_server(item, root, process_id):
    server = mcp_config.StdioServer(item["id"], _spec(item, root), root)
    server._termux = True
    server._termux_process_id = process_id
    return server


def _running_server(item, root):
    if not root:
        return None
    key = _key(root, item["id"])
    with _RUNNING_LOCK:
        server = _RUNNING.get(key)
        if server is not None:
            if server.alive():
                return server
            try:
                server.stop()
            except Exception:
                pass
            _RUNNING.pop(key, None)
            _forget_process(root, item)

        saved = _read_runtime_state(root).get(item["id"]) or {}
        process_id = str(saved.get("process_id") or "")
        if not process_id:
            return None
        server = _attached_server(item, root, process_id)
        if server.alive():
            _RUNNING[key] = server
            return server
        _forget_process(root, item)
        return None


def _installed_record(item, root):
    if not root:
        return {}
    try:
        record = mcp_config.read(root).get(item["id"]) or {}
    except OSError:
        return {}
    if record.get("bundle") != item["id"]:
        return {}
    if int(record.get("tested_at") or 0) <= 0 or int(record.get("tools") or 0) <= 0:
        return {}
    return record


def _lifecycle_status(item, runtime, installed, running, last_error):
    credential_missing = bool(item.get("credential_env_any") and not _credential(item)[1])
    if running:
        return "server_running"
    if credential_missing:
        return "permission_required"
    if runtime["unknown"]:
        return "termux_disconnected" if runtime["runtime"] == runtime_manager.TERMUX else "runtime_unavailable"
    if runtime["missing"]:
        return "tool_missing"
    if runtime["runtime"] == runtime_manager.TERMUX and not runtime["stdio"]:
        return "termux_disconnected"
    if runtime["runtime"] == runtime_manager.TERMUX and item["id"] == "filesystem":
        return "needs_setup"
    if installed and last_error:
        return "health_failed"
    if installed:
        return "server_stopped"
    return "ready"


def catalog(root=None):
    result = []
    for item in BUNDLES:
        runtime = _runtime_requirements(item)
        record = _installed_record(item, root)
        installed = bool(record)
        server = _running_server(item, root) if installed else None
        running = bool(server)
        key = _key(root, item["id"]) if root else None
        last_error = _LAST_ERRORS.get(key, "") if key else ""
        status = _lifecycle_status(item, runtime, installed, running, last_error)
        public = {
            k: v for k, v in item.items()
            if k not in {"command", "args", "env", "credential_env_any", "env_alias"}
        }
        process_id = str(getattr(server, "_termux_process_id", "") or "") if server else ""
        public.update({
            "available": status == "ready",
            "status": status,
            "missing": list(runtime["missing"]),
            "runtime": runtime["runtime"],
            "runtime_reason": runtime["reason"],
            "dependencies": list(item.get("runtimes") or []),
            "install_method": "on_demand" if item.get("command") in {"npx", "uvx"} else "manual_or_preinstalled",
            "start_method": "runtime_process_start(stdio=true)",
            "stop_method": "runtime_process_stop",
            "health_check": "live process status + MCP tools/list",
            "verified": installed,
            "installed": installed,
            "connected": running,
            "running": running,
            "can_start": installed and status in {"server_stopped", "health_failed"},
            "enabled": installed,
            "tools": int(record.get("tools") or 0) if installed else 0,
            "tested_at": int(record.get("tested_at") or 0) if installed else 0,
            "process_id": process_id,
            "health": "healthy" if running else ("failed" if status == "health_failed" else "stopped" if installed else "unverified"),
            "last_error": last_error,
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
            "use the localhost bridge before enabling this bundle."
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


def _start(item, root):
    if not _installed_record(item, root):
        raise ValueError("Install and verify this MCP bundle first")
    current = _running_server(item, root)
    if current is not None:
        return int(_installed_record(item, root).get("tools") or len(current.tools) or 0)

    runtime = _runtime_requirements(item)
    if runtime["unknown"]:
        raise RuntimeError(runtime["reason"])
    if runtime["missing"]:
        raise RuntimeError("Missing requirements: " + ", ".join(runtime["missing"]))
    if runtime["runtime"] == runtime_manager.TERMUX and item["id"] == "filesystem":
        raise RuntimeError("Filesystem MCP needs a shared project path before it can start")
    if runtime["runtime"] == runtime_manager.TERMUX and not runtime["stdio"]:
        raise RuntimeError("Termux localhost bridge is not available")

    server = mcp_config.StdioServer(item["id"], _spec(item, root), root)
    server.start(timeout=45)
    with _RUNNING_LOCK:
        _RUNNING[_key(root, item["id"])] = server
        _remember_process(root, item, server)
    return len(server.tools)


def _stop(item, root, require_running=False):
    key = _key(root, item["id"])
    with _RUNNING_LOCK:
        server = _RUNNING.get(key)
        saved = _read_runtime_state(root).get(item["id"]) or {}
        if server is None and saved.get("process_id"):
            server = _attached_server(item, root, str(saved["process_id"]))
        if server is None:
            if require_running:
                raise ValueError("MCP server is not running")
            _forget_process(root, item)
            return
        try:
            if getattr(server, "_termux", False) and getattr(server, "_termux_process_id", ""):
                runtime_manager.process_stop(server._termux_process_id)
                server._termux_process_id = ""
            else:
                server.stop()
        except Exception as exc:
            raise RuntimeError("MCP process could not be stopped") from exc
        finally:
            _RUNNING.pop(key, None)
        _forget_process(root, item)


def _health(item, root):
    server = _running_server(item, root)
    if server is None:
        return _test(item, root)
    tools = server._list_tools()
    if not isinstance(tools, list) or not tools:
        raise RuntimeError("MCP health check returned no tools")
    return len(tools)


def perform(root, bundle_id, action):
    item = _item(bundle_id)
    key = _key(root, item["id"])
    try:
        if action == "disable":
            _stop(item, root, require_running=False)
            with mcp_config.LOCK:
                servers = mcp_config.read(root)
                record = servers.get(item["id"])
                if not record or record.get("bundle") != item["id"]:
                    raise ValueError("Bundle is not enabled")
                del servers[item["id"]]
                mcp_config.save(root, servers)
            _LAST_ERRORS.pop(key, None)
            return {"ok": True, "enabled": False, "running": False}

        if action == "enable":
            count = _test(item, root)
            _save_enabled(item, root, count)
            _LAST_ERRORS.pop(key, None)
            return {"ok": True, "tools": count, "enabled": True, "running": False}

        if action == "test":
            count = _health(item, root)
            _LAST_ERRORS.pop(key, None)
            return {"ok": True, "tools": count, "running": _running_server(item, root) is not None}

        if action == "start":
            count = _start(item, root)
            _LAST_ERRORS.pop(key, None)
            return {"ok": True, "tools": count, "enabled": True, "running": True}

        if action == "stop":
            _stop(item, root, require_running=True)
            _LAST_ERRORS.pop(key, None)
            return {"ok": True, "enabled": True, "running": False}

        if action == "reconnect":
            if not _installed_record(item, root):
                raise ValueError("Install and verify this MCP bundle first")
            _stop(item, root, require_running=False)
            count = _start(item, root)
            _LAST_ERRORS.pop(key, None)
            return {"ok": True, "tools": count, "enabled": True, "running": True}

        raise ValueError("Unknown MCP lifecycle action")
    except (ValueError, KeyError, OSError, RuntimeError, TypeError, tools.ToolError) as exc:
        _LAST_ERRORS[key] = str(exc)[:300]
        raise


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
                "note": "Installed, process-running and health are separate live states. Running is claimed only while the managed process is alive.",
            })
            return True

        if method != "POST" or path == "/api/mcp-bundles":
            handler._json({"error": "Method not allowed"}, 405)
            return True

        root = _session_root(handler, data)
        action = path.rsplit("/", 1)[-1]
        handler._json(perform(root, data.get("id"), action))
    except (ValueError, KeyError, OSError, RuntimeError, TypeError, tools.ToolError) as error:
        message = str(error)
        if len(message) > 300:
            message = message[:300]
        handler._json({"error": "MCP lifecycle operation failed: " + message}, 400)
    return True
