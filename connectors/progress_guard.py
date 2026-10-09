"""Runtime guard against repeated 'start over' tool loops.

This is deliberately independent of the language model and of compaction.
A successful read/task_resume is information, NOT verified task progress.
Repeated identical reads cannot reset the compaction progress epoch or erase
the last meaningful checkpoint. Tool arguments are hashed, never logged.
"""
from __future__ import annotations

import hashlib
import json
import re

MAX_SIGNATURES = 24
REPEAT_LIMIT = 3
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
_READ_NAMES = frozenset((
    "task_resume", "task_list", "memory_recall", "project_rag_search",
    "git_status", "git_log", "git_diff", "observability_status",
    "observability_tail", "runtime_process_status", "tool_search",
))
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


def is_observation(name, args, kind):
    """True for calls that only retrieve known state, including shell probes."""
    if name in _READ_NAMES or kind == "read":
        return True
    if name in ("bash", "runtime_exec", "termux_exec"):
        return bool(_READ_COMMAND.match(str((args or {}).get("command") or "")))
    return False


def meaningful(name, kind, response):
    """Only verified tool-reported state changes reset no-progress compactions."""
    out = str(response or "")
    if _FAILURE.match(out) or _UNCHANGED.search(out):
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


class Guard:
    def __init__(self, session):
        self.session = session
        previous = getattr(session, "read_attempts", None)
        self.attempts = dict(previous) if isinstance(previous, dict) else {}
        self.halted = ""
        self.duplicate = ""

    def before(self, name, args, kind):
        """Return message if duplicate already seen. Third call is not executed."""
        if not is_observation(name, args, kind):
            return ""
        key = signature(name, args)
        count = min(REPEAT_LIMIT, int(self.attempts.get(key, 0)) + 1)
        self.attempts[key] = count
        while len(self.attempts) > MAX_SIGNATURES:
            del self.attempts[next(iter(self.attempts))]
        self.session.read_attempts = dict(self.attempts)
        self.duplicate = key if count >= 2 else ""
        if hasattr(self.session, "save_meta"):
            self.session.save_meta()
        if count >= REPEAT_LIMIT:
            self.halted = (
                "Stopped a no-progress loop: the same inspection (%s) was requested "
                "at least %d times without a verified change. Existing files were "
                "not deleted. The task is unfinished; continue by executing the next "
                "different action or reporting the exact missing permission/tool, "
                "not by restarting inspection." % (name, count)
            )
            return "error: " + self.halted
        return ""

    def after(self, name, args, kind, response):
        if meaningful(name, kind, response):
            self.attempts.clear()
            self.session.read_attempts = {}
            self.duplicate = ""
            self.session.compact_since_tool = 0
            if hasattr(self.session, "save_meta"):
                self.session.save_meta()
            return str(response)
        if self.duplicate and is_observation(name, args, kind):
            self.duplicate = ""
            return (str(response) + "\n\n[Runtime: this exact inspection has already "
                    "run. The task has NOT progressed. Do not inspect it again. "
                    "Choose a different action for the outstanding step, such as "
                    "opening the existing HTML in a browser, or report the precise "
                    "missing browser/phone capability.]")
        return str(response)

    def safe_message(self, objective):
        task = str(objective or "").strip()[:400]
        return (self.halted + ("\nActive task: " + task if task else "") +
                "\nStatus: unfinished; do not claim browser verification.")
