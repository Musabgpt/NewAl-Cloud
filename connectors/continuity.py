"""Deterministic conversation continuity for MusabAI.

A model-authored compaction is evidence, not a user message. Keep the actual
instructions and recoverable task state outside summaries, so even a bad/free
model summary cannot erase the task or impersonate the user.
"""
from __future__ import annotations

import json
import re

MAX_OBJECTIVE = 2000
MAX_SUMMARY = 3600
MAX_TOOL_EVIDENCE = 900
MAX_USER_TURNS = 24

_LEGACY_SUMMARY = re.compile(
    r"(?:^Summary of the conversation so far:|^Conversation compacted:|"
    r"</context>\s*Summary of the conversation so far:)", re.I | re.S
)
_ABANDONED = (
    re.compile(r"\b(?:i (?:don.t|do not|cannot) have (?:a |any )?task|"
               r"there(?: is|.s) (?:no|nothing) (?:task|to continue)|"
               r"what would you like (?:me )?to (?:do|work on)|"
               r"tell me (?:the goal|what you want)|"
               r"project (?:folder|directory) is empty.{0,60}nothing to)\b", re.I),
    re.compile(r"(?:ما (?:عندي|في|عندنا) (?:مهمة|شي)|"
               r"شو بدك (?:أعمل|اعمل)|"
               r"قلّي شو (?:بدك|المطلوب)|"
               r"لا توجد (?:مهمة|مهام)|"
               r"لم (?:تحدد|تُحدد) (?:مهمة|المهمة))"),
)


def _text(content):
    """Use only actual text; never turn model/tool payloads into instructions."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(str(part.get("text", "")) for part in content
                         if isinstance(part, dict) and part.get("type") == "text")
    return ""


def _actual_user(message):
    if message.get("role") != "user" or message.get("_internal"):
        return False
    body = _text(message.get("content", "")).strip()
    # Prior releases recorded the assistant-generated summary as a user turn.
    # It is not evidence of anything the user actually said.
    if _LEGACY_SUMMARY.search(body):
        return False
    return bool(body)


def _instruction(message):
    return str(message.get("_user_text") or _text(message.get("content", ""))).strip()


def _scope(messages, pinned):
    if not pinned:
        return messages
    from . import task_identity
    def from_start(start):
        if start and messages[start - 1].get("_continuity_note") and task_identity.matches(
                messages[start - 1].get("_task_anchor"), pinned):
            start -= 1
        return messages[start:]
    marked = [i for i, m in enumerate(messages) if _actual_user(m) and
              task_identity.matches(m.get("_task_anchor"), pinned)]
    if marked:
        return from_start(marked[0])
    # Migrate old transcripts whose user turns include injected runtime context.
    for i in reversed(range(len(messages))):
        m = messages[i]
        if not _actual_user(m):
            continue
        body = _instruction(m).split("</context>")[-1].strip()
        if task_identity.matches(body, pinned) or body.endswith("\n\n" + pinned):
            return from_start(i)
    return []


def _compact_user(message):
    """Remove repeated runtime boilerplate, preserving exact text and images."""
    if "_user_text" not in message:
        return message
    out = dict(message)
    content = message.get("content")
    text = message["_user_text"]
    # Keep project instructions from the original context block once.
    original = _text(content)
    if original.startswith("<context>") and "</context>" in original:
        text = original.split("</context>", 1)[0] + "</context>\n\n" + text
    if isinstance(content, list):
        out["content"] = [{"type": "text", "text": text}] + [
            p for p in content if isinstance(p, dict) and p.get("type") != "text"]
    else:
        out["content"] = text
    return out


def _compact_todo(todo):
    if not isinstance(todo, list):
        return ""
    rows = []
    for entry in todo[:12]:
        if isinstance(entry, dict):
            label = str(entry.get("text") or entry.get("content") or
                        entry.get("title") or entry.get("task") or "")[:145]
            status = str(entry.get("status") or "")[:30]
            if label:
                rows.append(("%s: " % status if status else "") + label)
        elif isinstance(entry, str):
            rows.append(entry[:145])
    return "; ".join(rows)[:1100]


def _recent_evidence(messages):
    """Keep a bounded trace; never say an operation succeeded just because it started."""
    rows = []
    for msg in reversed(messages):
        if msg.get("_continuity_note"):
            for value in reversed(msg.get("_tool_evidence") or []):
                if value not in rows:
                    rows.append(value)
                if len(rows) == 3:
                    break
            if len(rows) == 3:
                break
            continue
        if msg.get("role") != "tool":
            continue
        value = _text(msg.get("content"))
        if not value:
            continue
        rows.append("tool_result=%s %s" % (
            str(msg.get("tool_call_id") or "")[:55],
            re.sub(r"\s+", " ", value)[:170]))
        if len(rows) == 3:
            break
    return list(reversed(rows))


def compact_messages(session, summary, active_objective=""):
    """Return bounded history while preserving real user turns and active work.

    Never append a pretend user message or a synthetic 'I'll continue' turn.
    The original request survives repeated compactions unchanged.
    """
    messages = list(getattr(session, "messages", ()) or ())
    # One scope for user instructions, images, evidence and checkpoints.
    pinned = str(getattr(session, "active_task_anchor", "") or "").strip()
    scoped_messages = _scope(messages, pinned)
    real = [_compact_user(m) for m in scoped_messages if _actual_user(m)]
    if pinned and not real:
        real = [{"role": "user", "content": pinned, "_user_text": pinned,
                 "_task_anchor": pinned}]
    omitted = len(real) > MAX_USER_TURNS
    if omitted:
        real = [real[0]] + real[-(MAX_USER_TURNS - 1):]
    first = real[0] if real else None
    latest = real[-1] if real else None
    objective = str(active_objective or getattr(session, "active_objective", "")
                    or getattr(session, "goal", "") or "").strip()[:MAX_OBJECTIVE]
    if not objective and latest:
        objective = _text(latest.get("content")).split("</context>")[-1].strip()[:MAX_OBJECTIVE]

    # This text is deliberately an assistant-owned note, never a user instruction.
    summary = str(summary or "").strip()
    if pinned:
        # Untrusted model summaries can carry instructions for a previous task.
        summary = "[Prior model summary excluded after task isolation.]"
    if not summary or summary in ("(no summary)", "(none)", "No summary"):
        summary = "The automatic summary did not provide reliable details. Inspect the project and checkpoint."
    summary = summary[:MAX_SUMMARY]
    todo = _compact_todo(getattr(session, "todo", []))
    evidence_rows = _recent_evidence(scoped_messages)
    evidence = " | ".join(evidence_rows)[:MAX_TOOL_EVIDENCE]
    checkpoint = ""
    task_id = str(getattr(session, "active_task_id", "") or "")
    if task_id and getattr(session, "root", None):
        try:
            from . import task_state, task_identity
            row = task_state.resume(session.root, task_id=task_id)
            if row and row.get("status") == "active" and row.get("session_id") in (
                    None, "", getattr(session, "id", "")) and (
                    not pinned or task_identity.matches(row.get("objective"), pinned)):
                point = row.get("checkpoint") or {}
                checkpoint = "Progress: %s; Next: %s; Blocker: %s" % (
                    str(point.get("progress") or "")[:400],
                    str(point.get("next_step") or "")[:400],
                    str(point.get("blocker") or "")[:250])
        except Exception:
            pass
    parts = ["[Assistant conversation notes — not a new user message. "
             "These notes may be incomplete; verify claims with tools.]",
             summary,
             "[Durable task anchor — copied from the actual user turn/session, not inferred from the summary]",
             "Active request: " + (objective or "(unknown; inspect the real user messages)"),
             "Goal: " + str(getattr(session, "goal", "") or "")[:700],
             "Checklist: " + (todo or "(not recorded)"),
             "Current task checkpoint: " + (checkpoint or "(none)"),
             "Recent tool responses (not proof of overall completion): " + (evidence or "(none)"),
             "Keep executing the active request with available tools. "
             "Do not ask for a new task merely because this conversation was compacted. "
             "Do not claim completion without a verified result."]
    if omitted:
        parts.append("Older user turns are in the saved transcript; consult it before assuming their constraints.")
    note = {"role": "assistant", "content": "\n".join(parts),
            "_continuity_note": True, "_task_anchor": pinned,
            "_tool_evidence": evidence_rows}
    keep = []
    if first is not None:
        keep.append(first)
    keep.append(note)
    if latest is not None and latest is not first:
        keep.extend(real[1:])
    # For a single user turn, end on the original user request (not a fabricated turn).
    if latest is first and first is not None:
        keep = [note, first]
    return keep


def lost_task_reply(answer, objective):
    """Only catch explicit claims that no task exists; avoid generic short answers."""
    if not str(objective or "").strip():
        return False
    text = str(answer or "").strip()[:1800]
    return any(pattern.search(text) for pattern in _ABANDONED)


def correction(objective):
    return (
        "[Runtime continuity correction — not a new user request.] "
        "The actual active user task is: %s. "
        "The previous response incorrectly said there was no task. "
        "Continue with the actual tools and current project state. "
        "Do not invent completed actions or ask the user to repeat the task."
    ) % str(objective or "")[:MAX_OBJECTIVE]
