"""Runtime guard against repeated 'start over' tool loops.

This is deliberately independent of the language model and of compaction.
A successful read/task_resume is information, NOT verified task progress.
Repeated identical reads cannot reset the compaction progress epoch or erase
the last meaningful checkpoint. Tool arguments are hashed, never logged.

Read-only shell probes such as ``cd <dir> && find ... | head`` are
inspections. Many inspections in a row with no action between them form a loop
even when every probe has different arguments.
"""
from __future__ import annotations

import hashlib
import json
import re

MAX_SIGNATURES = 24
REPEAT_LIMIT = 3
# Exploring a project needs some inspections. This many in a row with no action
# between them means the agent is circling instead of acting.
CONSECUTIVE_INSPECTION_LIMIT = 10
_WARN_MARGIN = 3
_CONTINUE = re.compile(
    r"^\s*(?:continue|resume|carry on|keep going|pick up|"
    r"كمل|كمّل|تابع|أكمل|اكمل|استأنف|استكمال|واصل|كمل من حيث)\b",
    re.I,
)
_READ_COMMAND = re.compile(
    r"^\s*(?:pwd|ls|dir|cat|head|tail|less|wc|stat|find|grep|rg|"
    r"git\s+(?:status|log|diff|ls-files)|test\s+-[fe]|"
    r"python(?:3)?\s+-[Vv]|node\s+--version)\b", re.I,
)
_SHELL_SEPARATOR = re.compile(r"&&|\|\||;|\|")
_CD_COMMAND = re.compile(r"^\s*cd\b", re.I)
_FD_DUPLICATE = re.compile(r"\d*>&\d+")
_DEV_NULL = re.compile(r"\d*>\s*/dev/null")
_UNSAFE_SHELL = re.compile(r"(?:^|\s)-(?:delete|exec|execdir|ok|okdir)\b|\$\(|`")
_READ_NAMES = frozenset((
    "task_resume", "task_list", "memory_recall", "project_rag_search",
    "git_status", "git_log", "git_diff", "observability_status",
    "observability_tail", "runtime_process_status", "tool_search",
    "read", "glob", "grep",
))
_SHELL_NAMES = frozenset(("bash", "runtime_exec", "termux_exec"))
_CHANGED_NAMES = frozenset((
    "write", "edit", "apply_patch", "notebook_edit",
    "git_commit", "runtime_process_start", "phone",
))
_FAILURE = re.compile(
    r"^\s*(?:error:|not allowed:|denied:|blocked:|failed:|not found:)", re.I
)
_UNCHANGED = re.compile(
    r"\b(?:already has exactly this content|nothing changed|no changes)\b", re.I
)


def is_continuation(text):
    return bool(_CONTINUE.search(str(text or "")))


def is_read_only_shell(command):
    """True when every part of a shell line only inspects. A leading cd is allowed."""
    text = str(command or "")
    if not text.strip() or _UNSAFE_SHELL.search(text):
        return False
    text = _DEV_NULL.sub(" ", _FD_DUPLICATE.sub(" ", text))
    if ">" in text or "<<" in text:
        return False
    parts = [part.strip() for part in _SHELL_SEPARATOR.split(text)]
    parts = [part for part in parts if part and not _CD_COMMAND.match(part)]
    return bool(parts) and all(_READ_COMMAND.match(part) for part in parts)


def is_observation(name, args, kind):
    """True for calls that only retrieve known state, including shell probes."""
    if name == "phone":
        from . import phone
        return phone.looks_only(args) or (args or {}).get("action") in (
            "screenshot", "notifications_read", "automation_list", "crash_reports")
    if name in _READ_NAMES or kind == "read":
        return True
    if name in _SHELL_NAMES:
        return is_read_only_shell((args or {}).get("command"))
    return False


def meaningful(name, kind, response, args=None):
    """Only verified tool-reported state changes reset no-progress compactions."""
    out = str(response or "")
    if _FAILURE.match(out) or _UNCHANGED.search(out):
        return False
    if args is not None and is_observation(name, args, kind):
        return False
    return kind == "edit" or name in _CHANGED_NAMES


def signature(name, args):
    """Stable across compactions; never write raw arguments into session metadata."""
    try:
        packed = json.dumps([name, args], sort_keys=True, ensure_ascii=False,
                            separators=(",", ":"), default=str)
    except (TypeError, ValueError):
        packed = str(name)
    return hashlib.sha256(packed.encode("utf-8")).hexdigest()[:20]


def _count(value):
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0


class Guard:
    def __init__(self, session):
        self.session = session
        previous = getattr(session, "read_attempts", None)
        self.attempts = dict(previous) if isinstance(previous, dict) else {}
        self.inspections = _count(getattr(session, "consecutive_inspections", 0))
        self.halted = ""
        self.duplicate = ""

    def _persist(self):
        self.session.read_attempts = dict(self.attempts)
        self.session.consecutive_inspections = self.inspections
        if hasattr(self.session, "save_meta"):
            self.session.save_meta()

    def _run_message(self):
        return (
            "Stopped a no-progress loop: %d read-only inspections ran in a row "
            "with no action between them and no verified change. Existing files "
            "were not deleted. The task is unfinished; take the next different action "
            "(for example open the file on the device, edit it, or report the exact "
            "missing permission or tool), not another inspection." % self.inspections
        )

    def before(self, name, args, kind):
        """Return message if the call would loop. The looping call is not executed."""
        if not is_observation(name, args, kind):
            return ""
        key = signature(name, args)
        count = min(REPEAT_LIMIT, int(self.attempts.get(key, 0)) + 1)
        self.attempts[key] = count
        while len(self.attempts) > MAX_SIGNATURES:
            del self.attempts[next(iter(self.attempts))]
        self.inspections += 1
        self.duplicate = key if count >= 2 else ""
        self._persist()
        if count >= REPEAT_LIMIT:
            self.halted = (
                "Stopped a no-progress loop: the same inspection (%s) was requested "
                "at least %d times without a verified change. Existing files were "
                "not deleted. The task is unfinished; continue by executing the next "
                "different action or reporting the exact missing permission/tool, "
                "not by restarting inspection." % (name, count)
            )
            return "error: " + self.halted
        if self.inspections > CONSECUTIVE_INSPECTION_LIMIT:
            self.halted = self._run_message()
            return "error: " + self.halted
        return ""

    def after(self, name, args, kind, response):
        out = str(response or "")
        if meaningful(name, kind, response, args):
            self.attempts.clear()
            self.inspections = 0
            self.duplicate = ""
            self.halted = ""
            self.session.read_attempts = {}
            self.session.consecutive_inspections = 0
            self.session.compact_since_tool = 0
            if hasattr(self.session, "save_meta"):
                self.session.save_meta()
            return out
        if is_observation(name, args, kind):
            if self.duplicate:
                self.duplicate = ""
                out += ("\n\n[Runtime: this exact inspection has already "
                        "run. The task has NOT progressed. Do not inspect it again. "
                        "Choose a different action for the outstanding step, such as "
                        "opening the existing HTML in a browser, or report the precise "
                        "missing browser/phone capability.]")
            if self.inspections >= CONSECUTIVE_INSPECTION_LIMIT - _WARN_MARGIN:
                out += ("\n\n[Runtime: %d inspections in a row with no action. "
                        "Stop inspecting and take the next different action now.]"
                        % self.inspections)
            return out
        # Any attempted action ends the inspection run. A failed action does not.
        if self.inspections and not _FAILURE.match(out):
            self.inspections = 0
            self.session.consecutive_inspections = 0
            if hasattr(self.session, "save_meta"):
                self.session.save_meta()
        return out

    def safe_message(self, objective):
        task = str(objective or "").strip()[:400]
        return (self.halted + ("\nActive task: " + task if task else "") +
                "\nStatus: unfinished; do not claim browser verification.")
