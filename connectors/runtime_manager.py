"""Unified runtime manager for MusabAI.

The Android app process is not a Linux development shell. On Android, shell
programs such as node, npm, npx, python, git and bash belong to Termux and are
probed/executed there. ANDROID_NATIVE represents the app/phone bridge itself
and deliberately never depends on adb. REMOTE is an optional explicit HTTPS
execution backend.
"""
from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import threading
import time
import urllib.parse
import urllib.request

from . import tools

ANDROID_NATIVE = "ANDROID_NATIVE"
TERMUX = "TERMUX"
REMOTE = "REMOTE"
PRODUCT_RUNTIMES = (ANDROID_NATIVE, TERMUX, REMOTE)
TERMUX_BASE_COMMANDS = ("node", "npm", "npx", "python", "git", "bash")
NAMES = ["runtime_status", "runtime_exec"]

_CACHE_LOCK = threading.RLock()
_CACHE_AT = 0.0
_CACHE_VALUES = {}
_CACHE_STATE = ""


def _phone_available():
    try:
        from . import phone
        return bool(phone.available())
    except Exception:
        return False


def _connectors():
    from . import connectors
    return connectors


def _termux_record():
    if not _phone_available():
        return {"status": "unavailable", "error": "Android phone bridge unavailable"}
    try:
        data = _connectors().status()
    except Exception:
        return {"status": "unavailable", "error": "Android connector host unavailable"}
    for item in data.get("connectors") or []:
        if item.get("id") == "termux":
            return dict(item)
    return {"status": "unavailable", "error": "Termux connector state unavailable"}


def _native(op, **kwargs):
    return _connectors().native(op, **kwargs)


def _validated_commands(commands):
    out = []
    for value in commands or ():
        name = str(value or "").strip()
        if not re.fullmatch(r"[A-Za-z0-9._+-]{1,64}", name):
            raise ValueError("Invalid runtime command name")
        if name not in out:
            out.append(name)
    return out


def _clear_cache():
    global _CACHE_AT, _CACHE_VALUES, _CACHE_STATE
    with _CACHE_LOCK:
        _CACHE_AT = 0.0
        _CACHE_VALUES = {}
        _CACHE_STATE = ""


def probe_termux(commands=None, max_age=5.0):
    """Return tri-state command availability from Termux, never Android PATH.

    values are True/False when Termux was actually probed and None when the
    Termux connection is not ready, so callers do not misreport "npx missing".
    """
    global _CACHE_AT, _CACHE_VALUES, _CACHE_STATE
    requested = _validated_commands(commands or TERMUX_BASE_COMMANDS)
    record = _termux_record()
    state = str(record.get("status") or "unavailable")
    if state != "connected":
        return {
            "runtime": TERMUX,
            "status": state,
            "commands": {name: None for name in requested},
            "reason": record.get("error") or "Connect and test Termux before probing commands.",
        }

    now = time.monotonic()
    with _CACHE_LOCK:
        if _CACHE_STATE == state and now - _CACHE_AT <= max_age and all(name in _CACHE_VALUES for name in requested):
            return {
                "runtime": TERMUX,
                "status": "connected",
                "commands": {name: _CACHE_VALUES[name] for name in requested},
                "reason": "Command availability was verified inside Termux.",
            }

    probe_names = list(dict.fromkeys(list(TERMUX_BASE_COMMANDS) + requested))
    shell = (
        "for c in " + " ".join(shlex.quote(name) for name in probe_names) +
        '; do if command -v "$c" >/dev/null 2>&1; then printf "%s=1\\n" "$c"; '
        'else printf "%s=0\\n" "$c"; fi; done'
    )
    try:
        result = _native("termux_exec", command=shell)
        if result.get("status") == "running" and result.get("id"):
            for _ in range(3):
                time.sleep(0.05)
                result = _native("termux_result", id=result["id"])
                if result.get("status") != "running":
                    break
    except Exception:
        return {
            "runtime": TERMUX,
            "status": "error",
            "commands": {name: None for name in requested},
            "reason": "Termux command probe failed; availability is unknown.",
        }

    if result.get("status") != "completed" or result.get("exit_code") not in (0, None):
        return {
            "runtime": TERMUX,
            "status": str(result.get("status") or "error"),
            "commands": {name: None for name in requested},
            "reason": "Termux command probe did not complete successfully.",
        }

    values = {}
    for line in str(result.get("stdout") or "").splitlines():
        if "=" not in line:
            continue
        name, flag = line.split("=", 1)
        if name in probe_names and flag in ("0", "1"):
            values[name] = flag == "1"
    for name in probe_names:
        values.setdefault(name, None)

    with _CACHE_LOCK:
        _CACHE_AT = time.monotonic()
        _CACHE_VALUES = dict(values)
        _CACHE_STATE = "connected"

    return {
        "runtime": TERMUX,
        "status": "connected",
        "commands": {name: values.get(name) for name in requested},
        "reason": "Command availability was verified inside Termux.",
    }


def requirements(commands):
    """Resolve command requirements without confusing Android PATH with Termux."""
    requested = _validated_commands(commands)
    if _phone_available():
        probed = probe_termux(requested)
        values = probed["commands"]
        missing = [name for name in requested if values.get(name) is False]
        unknown = [name for name in requested if values.get(name) is None]
        return {
            "runtime": TERMUX,
            "missing": missing,
            "unknown": unknown,
            "reason": probed["reason"],
            "stdio": False,
        }

    # Development/CI host only. This is not the Android runtime decision path.
    missing = [name for name in requested if shutil.which(name) is None]
    return {
        "runtime": "LOCAL_HOST",
        "missing": missing,
        "unknown": [],
        "reason": "Checked on the non-Android development host.",
        "stdio": True,
    }


def command_status(command):
    state = requirements([command])
    name = _validated_commands([command])[0]
    if name in state["missing"]:
        available = False
    elif name in state["unknown"]:
        available = None
    else:
        available = True
    return {
        "command": name,
        "runtime": state["runtime"],
        "available": available,
        "reason": state["reason"],
        "stdio": state["stdio"],
    }


def _remote_config():
    raw = str(os.environ.get("NEWAL_REMOTE_RUNTIME_URL") or "").strip()
    if not raw:
        return {"configured": False, "url": "", "reason": "No remote runtime configured."}
    parsed = urllib.parse.urlsplit(raw)
    if (
        parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password
        or parsed.query or parsed.fragment or parsed.path not in ("", "/")
    ):
        return {"configured": False, "url": "", "reason": "Remote runtime must be an HTTPS origin."}
    return {"configured": True, "url": raw.rstrip("/"), "reason": "Remote HTTPS runtime configured."}


def snapshot(probe=False):
    native_ok = _phone_available()
    termux = _termux_record() if native_ok else {"status": "unavailable", "error": "Android phone bridge unavailable"}
    termux_row = {
        "runtime": TERMUX,
        "available": termux.get("status") == "connected",
        "status": termux.get("status") or "unavailable",
        "reason": termux.get("error") or "",
        "commands": {},
    }
    if probe and termux_row["available"]:
        checked = probe_termux(TERMUX_BASE_COMMANDS, max_age=0)
        termux_row["commands"] = checked["commands"]
        termux_row["reason"] = checked["reason"]

    remote = _remote_config()
    return {
        "runtimes": [
            {
                "runtime": ANDROID_NATIVE,
                "available": native_ok,
                "requires_adb": False,
                "shell": False,
                "reason": "Local app/phone bridge; Android actions use the native localhost bridge, never adb.",
            },
            termux_row,
            {
                "runtime": REMOTE,
                "available": remote["configured"],
                "configured": remote["configured"],
                "reason": remote["reason"],
            },
        ],
        "shell_commands": list(TERMUX_BASE_COMMANDS),
        "policy": "On Android, shell command discovery and execution use Termux instead of the app sandbox.",
    }


def _remote_exec(command):
    cfg = _remote_config()
    if not cfg["configured"]:
        raise tools.ToolError(cfg["reason"])
    body = json.dumps({"command": command}).encode("utf-8")
    req = urllib.request.Request(
        cfg["url"] + "/exec",
        data=body,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    token = str(os.environ.get("NEWAL_REMOTE_RUNTIME_TOKEN") or "").strip()
    if token:
        req.add_header("Authorization", "Bearer " + token)
    try:
        with urllib.request.urlopen(req, timeout=60) as response:
            raw = response.read(1_000_001)
    except Exception as exc:
        raise tools.ToolError("Remote runtime request failed") from exc
    if len(raw) > 1_000_000:
        raise tools.ToolError("Remote runtime response exceeded 1 MB")
    try:
        data = json.loads(raw.decode("utf-8"))
    except Exception as exc:
        raise tools.ToolError("Remote runtime returned invalid JSON") from exc
    if not isinstance(data, dict):
        raise tools.ToolError("Remote runtime returned invalid JSON")
    return data


def execute(command, runtime=None):
    if not isinstance(command, str) or not command.strip() or len(command) > 131072:
        raise tools.ToolError("Provide a non-empty command up to 131072 characters")
    requested = str(runtime or "").strip().upper()
    if requested and requested not in PRODUCT_RUNTIMES:
        raise tools.ToolError("runtime must be ANDROID_NATIVE, TERMUX or REMOTE")

    if requested:
        chosen = requested
    elif _phone_available():
        chosen = TERMUX
    elif _remote_config()["configured"]:
        chosen = REMOTE
    else:
        raise tools.ToolError("No supported runtime is available")

    if chosen == ANDROID_NATIVE:
        raise tools.ToolError(
            "ANDROID_NATIVE is the local phone/app bridge and does not run shell commands or adb. "
            "Use the phone tool for Android actions, or TERMUX for shell commands."
        )

    if chosen == TERMUX:
        state = _termux_record()
        if state.get("status") != "connected":
            raise tools.ToolError(state.get("error") or "Connect and test Termux before running commands")
        result = _native("termux_exec", command=command)
        return {
            "runtime": TERMUX,
            "id": result.get("id"),
            "status": result.get("status"),
            "exit_code": result.get("exit_code"),
            "stdout": str(result.get("stdout") or ""),
            "stderr": str(result.get("stderr") or ""),
            "command_success": result.get("command_success"),
        }

    data = _remote_exec(command)
    data.setdefault("runtime", REMOTE)
    return data


def install():
    @tools.tool(
        "runtime_status",
        "Inspect MusabAI runtime state. On Android, probes node/npm/npx/python/git/bash inside Termux, not the Android app sandbox.",
        {"probe": {"type": "boolean", "description": "when true, verify the standard shell commands inside Termux"}},
        [],
        "meta",
    )
    def runtime_status(ctx, probe=False):
        data = snapshot(bool(probe))
        return json.dumps(data, ensure_ascii=False), {"runtime_count": len(data["runtimes"])}

    @tools.tool(
        "runtime_exec",
        "Run a shell command through the unified runtime manager. Android shell commands execute in connected Termux; ANDROID_NATIVE never invokes adb.",
        {
            "command": {"type": "string", "description": "shell command"},
            "runtime": {
                "type": "string",
                "enum": [ANDROID_NATIVE, TERMUX, REMOTE],
                "description": "optional explicit runtime; auto prefers Termux on Android",
            },
        },
        ["command"],
        "exec",
    )
    def runtime_exec(ctx, command, runtime=None):
        data = execute(command, runtime)
        return json.dumps(data, ensure_ascii=False), {
            "runtime": data.get("runtime"),
            "exit": data.get("exit_code"),
            "pending": data.get("status") == "running",
        }
