"""Deterministic task ownership for one MusabAI conversation.

A shared workspace can hold multiple unfinished tasks. Never resume the most
recent *workspace* task when the user says 'كمل'; resume only this conversation's
explicitly anchored objective/id. An assistant summary is not task authority.
"""
from __future__ import annotations

import re

_CONTINUE = re.compile(
    r"^\s*(?:كمل|كمّل|تابع|أكمل|اكمل|استأنف|واصل|continue|resume|keep going|carry on|pick up)\b",
    re.I,
)


def continuation(text):
    return bool(_CONTINUE.search(str(text or "").strip()))


def normalized(text):
    return " ".join(str(text or "").casefold().split())


def matches(left, right):
    return bool(normalized(left)) and normalized(left) == normalized(right)


_TOPICS = (
    ("game", "لعب", "html", "canvas", "طيارة", "دبابة"),
    ("whatsapp", "واتساب", "واتس"),
    ("gmail", "بريد", "ايميل", "email"),
    ("browser", "متصفح", "chrome", "playwright"),
    ("github", "مستودع", "repository", "git"),
)

_FOLLOWUP = re.compile(
    r"^(?:(?:نعم|اجل|أجل|تمام|طيب|اوكي|ok|okay|yes|do it|go ahead)[.!؟?\s]*$|"
    r"(?:fix it|test it|run it|make it|change it|try again|اختبرها|اختبره|شغلها|شغله|"
    r"صلحها|صلحه|عدّلها|عدلها|عدل عليه|خلي|خلّي|خليه|خليها|غير لون|جرّب|جرب)\b)", re.I,
)


def _reset_working_state(session):
    session.read_attempts = {}
    session.consecutive_inspections = 0
    session.compact_since_tool = 0
    session.todo = []
    session.goal = ""
    session.goal_progress = 0


def same_project_followup(previous, instruction):
    """Explicitly reuse the task only when both turns name its domain."""
    a, b = normalized(previous), normalized(instruction)
    for terms in _TOPICS:
        if any(t in a for t in terms) and any(t in b for t in terms):
            return True
    return False


def activate(session, instruction):
    """Anchor an actual user message before supervisor creation.

    Preserve an interrupted task's filesystem checkpoint, but never carry the
    former task's Todo list into a distinct command such as 'افتح واتساب'.
    """
    instruction = str(instruction or "").strip()[:2000]
    prior = str(getattr(session, "active_task_anchor", "") or
                getattr(session, "active_objective", "") or "").strip()
    session._task_migrated = bool(prior and not getattr(session, "active_task_anchor", ""))
    if session._task_migrated:
        # Old releases never assigned the checklist to an objective. Its ownership
        # cannot be proven; recover progress from the matching durable checkpoint.
        # The old transcript and project files remain intact.
        _reset_working_state(session)
        session.active_task_anchor = prior
    if prior:
        session.active_objective = prior
    if continuation(instruction):
        if prior and not continuation(prior):
            session.active_objective = prior
            if not getattr(session, "active_task_anchor", ""):
                session.active_task_anchor = prior
            return prior
        session.active_objective = instruction
        session.active_task_anchor = instruction
        session.active_task_id = ""
        return instruction

    related = bool(prior and (matches(prior, instruction) or
                             same_project_followup(prior, instruction) or
                             (_FOLLOWUP.search(instruction) and not (
                                 any(t in normalized(instruction) for terms in _TOPICS for t in terms)
                                 and not same_project_followup(prior, instruction)))))
    if related:
        # 'شغل اللعبة' is the next step of the existing game, not a new game.
        return prior
    switched = bool(prior and not matches(prior, instruction))
    session.active_objective = instruction
    session.active_task_anchor = instruction
    session.active_task_id = ""
    if switched:
        _reset_working_state(session)
    return instruction


def previous_checkpoint(session, continuation_request):
    """Only recover a checkpoint anchored to the active task of THIS session."""
    if not continuation_request:
        return None
    from . import task_state

    target = str(getattr(session, "active_objective", "") or "").strip()
    if not target or continuation(target):
        return None
    pinned = str(getattr(session, "active_task_id", "") or "")
    candidate = None
    if pinned:
        candidate = task_state.resume(session.root, task_id=pinned)
    else:
        # Migration for existing sessions without an active_task_id: pick only a
        # same-objective record, never blindly the newest project checkpoint.
        rows = task_state.list_tasks(session.root, session_id=session.id, limit=64)
        for row in rows:
            if matches(row.get("objective"), target):
                candidate = task_state.resume(session.root, task_id=row["id"])
                break
    if not candidate or candidate.get("status") != "active":
        return None
    if not matches(candidate.get("objective"), target):
        return None
    if candidate.get("session_id") not in (None, "", session.id):
        return None
    return candidate
