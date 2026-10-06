"""Phase 9 verification evidence ledger for MusabAI.

This module records privacy-safe verification metadata for effectful actions.
It never stores prompts, tool arguments, command output, file contents, tokens,
or credentials. An action returning success is not automatically considered
independently verified.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import threading
import time

from . import tools

NAMES = ["verification_status", "verification_tail"]
_LOCK = threading.RLock()
MAX_BYTES = 2 * 1024 * 1024
MAX_TAIL = 100
_WRITEISH = re.compile(
    r"(create|update|delete|write|edit|apply|send|post|commit|merge|push|install|upload|"
    r"archive|trash|label|move|rename|reply|forward|schedule|cancel|tap|type|swipe|open_app)",
    re.I,
)
_PHONE_READ = {"screen", "screenshot", "notifications_read", "automation_list", "crash_reports", "wait"}


def _home():
    root = Path(os.environ.get("NEWAL_VERIFICATION_HOME") or (
        Path(os.environ.get("NEWAL_CODE_HOME") or Path.home() / ".newal-code") / "verification"
    ))
    root.mkdir(parents=True, exist_ok=True)
    return root


def _project_id(root):
    return hashlib.sha256(os.path.abspath(str(root or "")).encode("utf-8")).hexdigest()[:16]


def _path(root):
    return _home() / (_project_id(root) + ".jsonl")


def _rotate(path):
    try:
        if path.stat().st_size <= MAX_BYTES:
            return
    except OSError:
        return
    backup = path.with_suffix(".jsonl.1")
    try:
        backup.unlink(missing_ok=True)
        path.replace(backup)
    except OSError:
        pass


def _safe_scalar(value):
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return str(value)[:120]


def classify(name, kind, ok, meta=None, args=None):
    """Return failed, verified, needs_verification, or neutral."""
    meta = dict(meta or {})
    args = dict(args or {})
    if not ok:
        return "failed"
    exit_code = meta.get("exit")
    if exit_code is None:
        exit_code = meta.get("exit_code")
    if exit_code is None:
        exit_code = meta.get("returncode")
    if exit_code is not None:
        return "verified" if exit_code == 0 else "failed"

    name = str(name or "")
    kind = str(kind or "")
    if kind == "edit":
        return "needs_verification"
    if kind == "connector_write":
        return "needs_verification"
    if kind == "exec":
        # Launching a process without a reported exit is not proof that it completed.
        return "needs_verification"
    if name == "phone":
        action = str(args.get("action") or "")
        return "neutral" if action in _PHONE_READ else "needs_verification"
    if kind == "mcp" and _WRITEISH.search(name):
        return "needs_verification"
    if name in ("task_complete",):
        return "needs_verification"
    if name in ("task_checkpoint", "task_resume", "task_list", "verification_status", "verification_tail"):
        return "neutral"
    return "neutral"


def record(root, name, kind, ok, meta=None, args=None, source="tool"):
    status = classify(name, kind, ok, meta, args)
    row = {
        "t": round(time.time(), 3),
        "source": str(source or "tool")[:32],
        "name": str(name or "")[:100],
        "kind": str(kind or "")[:40],
        "status": status,
    }
    meta = dict(meta or {})
    for key in ("exit", "exit_code", "returncode", "timed_out"):
        if key in meta:
            row[key] = _safe_scalar(meta[key])
    path = _path(root)
    try:
        with _LOCK:
            _rotate(path)
            with path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
    except OSError:
        pass
    return row


def record_project_check(root, command, ok, exit_code=None):
    # Do not store the command text; only record that the project's verifier ran.
    row = {
        "t": round(time.time(), 3),
        "source": "project_check",
        "name": "project_tests",
        "kind": "verification",
        "status": "verified" if ok else "failed",
    }
    if exit_code is not None:
        row["exit"] = _safe_scalar(exit_code)
    path = _path(root)
    try:
        with _LOCK:
            _rotate(path)
            with path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
    except OSError:
        pass
    return row


def feedback(row):
    status = (row or {}).get("status")
    if status == "needs_verification":
        return (
            "\n\nVerification required: this action reported success but its resulting state was not "
            "independently checked. Read back the state or run the relevant test before claiming completion. "
            "If verification fails, diagnose the evidence and change the approach instead of blindly repeating the same call."
        )
    return ""


def _read(root, limit=50):
    try:
        limit = max(1, min(int(limit or 50), MAX_TAIL))
    except (TypeError, ValueError):
        raise tools.ToolError("limit must be an integer")
    path = _path(root)
    if not path.exists():
        return []
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    rows = []
    for line in lines[-limit:]:
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if isinstance(row, dict):
            rows.append({k: row[k] for k in (
                "t", "source", "name", "kind", "status", "exit", "exit_code", "returncode", "timed_out"
            ) if k in row})
    return rows


def status(root):
    rows = _read(root, MAX_TAIL)
    counts = {"verified": 0, "failed": 0, "needs_verification": 0, "neutral": 0}
    for row in rows:
        state = row.get("status")
        if state in counts:
            counts[state] += 1
    return {
        "local": True,
        "records_payloads": False,
        "recent_events": len(rows),
        "counts": counts,
        "latest": rows[-1] if rows else None,
    }


def install():
    @tools.tool(
        "verification_status",
        "Show privacy-safe local verification evidence for the current project. No prompts, arguments, outputs or credentials are stored.",
        {},
        [],
        "read",
    )
    def verification_status(ctx):
        result = status(ctx.session.root)
        return json.dumps(result, ensure_ascii=False), {"verification": "status"}

    @tools.tool(
        "verification_tail",
        "Read recent privacy-safe verification metadata for the current project.",
        {"limit": {"type": "integer", "description": "1-100 recent verification events"}},
        [],
        "read",
    )
    def verification_tail(ctx, limit=50):
        rows = _read(ctx.session.root, limit)
        return json.dumps(rows, ensure_ascii=False), {"verification": "tail", "events": len(rows)}
