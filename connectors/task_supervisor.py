"""Task supervision for long MusabAI turns.

This layer does not replace durable task_state. It coordinates the existing
agent cancel path, provider streaming cancellation and task checkpoints so a
turn cannot remain "working" forever without observable progress.
"""
from __future__ import annotations

import os
import re
import threading
import time

from . import task_state

_PROGRESS_EVENTS = frozenset({
    "turn_start", "status", "text_delta", "reasoning_delta", "assistant",
    "tool_intent", "tool_start", "tool_end", "output", "usage",
    "verify_start", "verify", "goal_check", "goal", "todo",
})
_CONTINUATION = re.compile(
    r"\b(continue|resume|carry on|pick up|keep going|where we stopped)\b|"
    r"(كمل|كمّل|اكمل|أكمل|تابع|استأنف|استكمال|من حيث توقفنا)",
    re.I,
)
_MULTI_STEP = re.compile(
    r"\b(long|multi[- ]?step|phase|migration|implement|build|project|refactor|"
    r"fix.*test|test.*fix|end[- ]?to[- ]?end)\b|"
    r"(مهمة كبيرة|عدة خطوات|متعدد الخطوات|مرحلة|مراحل|مشروع|تنفيذ|بناء|إصلاح.*اختبار)",
    re.I,
)


def _number(name, default, minimum):
    try:
        value = float(os.environ.get(name, default))
    except (TypeError, ValueError):
        value = float(default)
    return max(float(minimum), value)


class CancelToken:
    """Event-like token combining user stop, watchdog stall and hard timeout."""

    def __init__(self, user_event):
        self.user_event = user_event
        self.watchdog_event = threading.Event()
        self.hard_event = threading.Event()
        self._reason = ""
        self._lock = threading.RLock()

    def is_set(self):
        return self.user_event.is_set() or self.watchdog_event.is_set() or self.hard_event.is_set()

    def wait(self, timeout=None):
        if self.is_set():
            return True
        end = None if timeout is None else time.monotonic() + max(0.0, float(timeout))
        while True:
            if self.is_set():
                return True
            if end is not None:
                left = end - time.monotonic()
                if left <= 0:
                    return False
                delay = min(0.05, left)
            else:
                delay = 0.05
            if self.user_event.wait(delay):
                return True

    def reason(self):
        if self.user_event.is_set():
            return "user"
        if self.hard_event.is_set():
            return "hard_timeout"
        if self.watchdog_event.is_set():
            return self._reason or "watchdog_stall"
        return ""

    def trigger_watchdog(self, reason="watchdog_stall"):
        with self._lock:
            if self.user_event.is_set() or self.hard_event.is_set() or self.watchdog_event.is_set():
                return False
            self._reason = reason
            self.watchdog_event.set()
            return True

    def trigger_hard_timeout(self):
        with self._lock:
            if self.user_event.is_set() or self.hard_event.is_set():
                return False
            self._reason = "hard_timeout"
            self.hard_event.set()
            return True

    def consume_watchdog(self):
        with self._lock:
            if not self.watchdog_event.is_set():
                return False
            self.watchdog_event.clear()
            if not self.hard_event.is_set():
                self._reason = ""
            return True


class TaskSupervisor:
    """Heartbeat/watchdog/checkpoint coordinator for one top-level agent turn."""

    def __init__(self, session, user_cancel, raw_emit, objective, turn):
        self.session = session
        self.objective = str(objective or "")[:task_state.MAX_OBJECTIVE]
        self.turn = int(turn or 0)
        self.raw_emit = raw_emit
        self.cancel_token = CancelToken(user_cancel)
        self.heartbeat_s = _number("NEWAL_SUPERVISOR_HEARTBEAT_SECONDS", 15, 0.05)
        self.stall_s = _number("NEWAL_SUPERVISOR_STALL_SECONDS", 240, self.heartbeat_s * 2)
        self.hard_s = _number("NEWAL_SUPERVISOR_HARD_TIMEOUT_SECONDS", 1800, self.stall_s * 2)
        try:
            self.max_recoveries = max(1, min(8, int(os.environ.get("NEWAL_SUPERVISOR_MAX_RECOVERIES", "3"))))
        except ValueError:
            self.max_recoveries = 3
        self.started_at = time.monotonic()
        self.last_progress_at = self.started_at
        self.last_heartbeat_at = 0.0
        self.last_checkpoint_at = 0.0
        self.last_event = "start"
        self.last_tool = ""
        self.step = 0
        self.recoveries = 0
        self.task_id = "auto-%s-turn-%d" % (str(session.id)[:40], self.turn)
        self._stop = threading.Event()
        self._lock = threading.RLock()
        try:
            self.previous = task_state.resume(session.root)
        except Exception:
            self.previous = None
        self._thread = None

    def resume_context(self, text):
        row = self.previous
        if not row or row.get("status") != "active" or not _CONTINUATION.search(str(text or "")):
            return ""
        cp = row.get("checkpoint") or {}
        return (
            "Durable task checkpoint found. Resume from it instead of guessing. "
            "Task id: %s. Objective: %s. Last progress: %s. Next step: %s. Blocker: %s."
            % (
                row.get("id", ""),
                str(row.get("objective") or "")[:700],
                str(cp.get("progress") or "")[:700],
                str(cp.get("next_step") or "")[:700],
                str(cp.get("blocker") or "")[:500],
            )
        )

    def planning_context(self, text):
        text = str(text or "")
        if len(text) < 240 and not _MULTI_STEP.search(text):
            return ""
        return (
            "Task supervisor: treat this as multi-step work. Keep a short concrete checklist, "
            "finish one verifiable step at a time, and change route instead of repeating a stuck action."
        )

    def _emit(self, ev):
        if not self.raw_emit:
            return
        data = dict(ev)
        data.setdefault("session", self.session.id)
        data.setdefault("t", round(time.time(), 3))
        try:
            self.raw_emit(data)
        except Exception:
            pass

    def _checkpoint(self, progress="", next_step="", blocker="", evidence=""):
        now = time.monotonic()
        try:
            row = task_state.checkpoint(
                self.session.root,
                task_id=self.task_id,
                objective=self.objective,
                progress=progress,
                next_step=next_step,
                blocker=blocker,
                evidence=evidence,
            )
            self.last_checkpoint_at = now
            return row
        except Exception:
            return None

    def start(self):
        self._checkpoint(
            progress="Supervised turn started.",
            next_step="Continue from agent step 0.",
            evidence="session=%s turn=%d" % (self.session.id, self.turn),
        )
        self._thread = threading.Thread(target=self._watchdog, name="musabai-task-watchdog", daemon=True)
        self._thread.start()

    def observe(self, ev):
        kind = str((ev or {}).get("type") or "")
        if kind not in _PROGRESS_EVENTS:
            return
        now = time.monotonic()
        with self._lock:
            self.last_progress_at = now
            self.last_event = kind
            try:
                self.step = max(self.step, int((ev or {}).get("step") or 0))
            except (TypeError, ValueError):
                pass
            if kind == "tool_start":
                self.last_tool = str((ev or {}).get("name") or "")[:120]
        if kind == "tool_end":
            ok = bool((ev or {}).get("ok"))
            name = str((ev or {}).get("name") or self.last_tool or "tool")
            self._checkpoint(
                progress="%s %s at agent step %d." % ("Completed" if ok else "Tool failed:", name, self.step),
                next_step="Continue from the next agent step; do not repeat an unchanged failing action.",
                evidence=("ok" if ok else "failed") + " tool=" + name,
            )
        elif kind == "verify":
            ok = (ev or {}).get("ok")
            self._checkpoint(
                progress="Verification %s at agent step %d." % ("passed" if ok else "did not pass", self.step),
                next_step="Continue from the verified state." if ok else "Fix the verified failure before moving on.",
                evidence=str((ev or {}).get("command") or "")[:task_state.MAX_EVIDENCE],
            )

    def mark_progress(self, label="recovery"):
        with self._lock:
            self.last_progress_at = time.monotonic()
            self.last_event = str(label or "recovery")

    def consume_watchdog(self):
        if not self.cancel_token.consume_watchdog():
            return False
        self.mark_progress("watchdog-recovery")
        return True

    def _watchdog(self):
        poll = min(0.25, max(0.02, self.heartbeat_s / 4))
        while not self._stop.wait(poll):
            if self.cancel_token.user_event.is_set():
                return
            now = time.monotonic()
            elapsed = now - self.started_at
            idle = now - self.last_progress_at
            if now - self.last_heartbeat_at >= self.heartbeat_s:
                self.last_heartbeat_at = now
                self._emit({
                    "type": "task_heartbeat",
                    "step": self.step,
                    "elapsed": round(elapsed, 1),
                    "idle": round(idle, 1),
                    "last_event": self.last_event,
                    "tool": self.last_tool,
                })
            if elapsed >= self.hard_s:
                if self.cancel_token.trigger_hard_timeout():
                    self._checkpoint(
                        progress="Stopped by the hard task timeout.",
                        next_step="Resume from the last completed checkpoint with a smaller bounded step.",
                        blocker="Hard timeout after %.1f seconds." % elapsed,
                    )
                    self._emit({"type": "status", "text": "Task timeout reached; stopping safely…"})
                return
            if idle >= self.stall_s and not self.cancel_token.watchdog_event.is_set():
                if self.recoveries >= self.max_recoveries:
                    if self.cancel_token.trigger_hard_timeout():
                        self._checkpoint(
                            progress="Stopped after repeated watchdog recoveries.",
                            next_step="Resume from the last completed checkpoint and choose a different route.",
                            blocker="Repeated stalls without progress.",
                        )
                        self._emit({"type": "status", "text": "Repeated stalls detected; stopping safely…"})
                    return
                if self.cancel_token.trigger_watchdog():
                    self.recoveries += 1
                    self._checkpoint(
                        progress="Watchdog detected no progress.",
                        next_step="Retry from the last completed step using another provider/tool or a smaller action.",
                        blocker="No progress for %.1f seconds." % idle,
                        evidence="watchdog recovery %d/%d" % (self.recoveries, self.max_recoveries),
                    )
                    self._emit({
                        "type": "status",
                        "text": "No progress detected; cancelling the stuck operation and trying another route…",
                    })

    def request_stop(self, reason="user"):
        self._checkpoint(
            progress="Turn paused safely.",
            next_step="Resume from the last completed checkpoint.",
            blocker="Stopped by user." if reason == "user" else str(reason or "stopped"),
        )
        self._emit({"type": "status", "text": "Stopping the active operation…"})
        self.cancel_token.user_event.set()

    def finish(self, error="", answer=""):
        self._stop.set()
        reason = self.cancel_token.reason()
        if not error and reason not in ("user", "hard_timeout"):
            try:
                task_state.complete(
                    self.session.root,
                    self.task_id,
                    ("Verified turn finished. " + str(answer or "")).strip()[:task_state.MAX_FIELD],
                )
            except Exception:
                pass
            return
        blocker = "Stopped by user." if reason == "user" or error == "interrupted" else (
            "Hard task timeout." if reason == "hard_timeout" or error == "timeout" else str(error or reason or "unfinished")
        )
        self._checkpoint(
            progress="Turn ended before completion.",
            next_step="Resume from the last completed checkpoint.",
            blocker=blocker,
        )

    def snapshot(self):
        now = time.monotonic()
        return {
            "active": not self._stop.is_set(),
            "task_id": self.task_id,
            "turn": self.turn,
            "step": self.step,
            "elapsed": round(now - self.started_at, 1),
            "idle": round(now - self.last_progress_at, 1),
            "recoveries": self.recoveries,
            "reason": self.cancel_token.reason(),
            "last_event": self.last_event,
            "tool": self.last_tool,
        }
