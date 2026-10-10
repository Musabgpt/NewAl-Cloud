"""Evidence-based completion and bounded replay protection, independent of the LLM.

Only a narrow single-action contract may finish automatically. Complex work
keeps its normal verification/goal/stop-hook gates. A cached successful action
is NOT proof that an entire multi-step task is complete.
"""
from __future__ import annotations

import re
import unicodedata

from . import progress_guard, task_identity

_RESUME_ONLY = re.compile(r"^(?:كمل|كمّل|تابع|أكمل|اكمل|استأنف|واصل|continue|resume|keep going|carry on)[.!؟?\s]*$", re.I)
_OPEN = re.compile(r"^(?:please\s+)?(?:open|launch|افتح|شغل|شغّل)\s+(?:(?:the\s+)?app\s+|تطبيق\s+|برنامج\s+)?(.+?)\s*[.!؟?]*$", re.I)
_ALIASES = {
    "whatsapp": "com.whatsapp", "واتساب": "com.whatsapp", "واتس اب": "com.whatsapp",
    "واتس آب": "com.whatsapp", "واتس": "com.whatsapp",
    "chrome": "com.android.chrome", "google chrome": "com.android.chrome", "كروم": "com.android.chrome",
    "telegram": "org.telegram.messenger", "تلغرام": "org.telegram.messenger", "تيليجرام": "org.telegram.messenger",
}
# Screen-coordinate gestures may intentionally repeat on changing UI state.
# Do not cache those using arguments alone. These actions have stable targets.
_PHONE_EFFECTS = frozenset(("open_app", "open_url", "alarm", "timer", "torch", "volume",
    "notify", "share", "sms", "call", "settings", "intent", "install_apk", "automation_replay"))
_FILE_EFFECTS = frozenset(("write", "edit", "apply_patch", "notebook_edit"))


def _normal(value):
    value = unicodedata.normalize("NFKC", str(value or "")).casefold().strip(" .!؟?")
    value = "".join(c for c in value if not unicodedata.combining(c))
    return " ".join(value.split())


def app_identity(value):
    value = _normal(value)
    return _ALIASES.get(value, value)


def open_target(instruction):
    match = _OPEN.fullmatch(str(instruction or "").strip())
    if not match:
        return ""
    target = re.sub(r"\s+(?:on (?:the |my )?(?:phone|device)|على (?:الهاتف|الجهاز|الموبايل))$",
                    "", match[1], flags=re.I)
    # Match the WHOLE target with a tool argument/receipt later; never extract
    # 'WhatsApp' out of 'WhatsApp then send ...', a negation, or a question.
    return app_identity(target)


def repeat_limit(instruction):
    """Respect an explicit bounded repeat request; unrequested repetition is one."""
    text = _normal(instruction)
    match = re.search(r"\b(\d+)\s*(?:times|مرات)\b", text)
    if match:
        return max(1, int(match[1]))
    return 2 if re.search(r"\b(?:twice|مرتين)\b", text) else 1


def successful(meta, text):
    if any(meta.get(k) for k in ("error", "isError", "pending")) or meta.get("ok") is False:
        return False
    if meta.get("status") in ("running", "pending", "queued", "failed", "error"):
        return False
    if any(meta.get(k) not in (None, 0) for k in ("exit", "exit_code", "returncode")):
        return False
    native = meta.get("phone")
    if isinstance(native, dict) and (native.get("ok") is not True or native.get("pending")):
        return False
    return not progress_guard._FAILURE.match(str(text or ""))


class CompletionGuard:
    def __init__(self, session, instruction):
        self.session = session
        self.anchor = str(getattr(session, "active_task_anchor", "") or instruction)
        prior = getattr(session, "action_state", None)
        resume = bool(_RESUME_ONLY.fullmatch(str(instruction or "").strip()))
        self.state = dict(prior) if (resume and isinstance(prior, dict) and
                                    task_identity.matches(prior.get("anchor"), self.anchor)) else {}
        self.state["anchor"] = self.anchor
        self.state.setdefault("receipt", {})
        self.state.setdefault("terminal", "")
        self.state.setdefault("repeat_limit", repeat_limit(instruction))
        self.target = open_target(self.anchor if resume else instruction)
        self.replays = 0
        self.halted = ""
        self.last_failed = False
        self._candidate = ""
        self._persist()

    def _persist(self):
        self.session.action_state = self.state
        self.session.save_meta()

    def _key(self, name, args, kind):
        if name == "phone" and args.get("action") in _PHONE_EFFECTS:
            clean = {k: v for k, v in args.items() if v not in (None, "")}
            if clean.get("action") == "open_app":
                clean["name"] = app_identity(clean.get("name"))
            return progress_guard.signature(name, clean)
        if name in _FILE_EFFECTS or (name in ("bash", "runtime_exec", "termux_exec") and
                                     not progress_guard.is_observation(name, args, kind)):
            return progress_guard.signature(name, args)
        return ""

    def replay(self, name, args, kind):
        key = self._key(name, args, kind)
        receipt = self.state.get("receipt") or {}
        if not key or key != receipt.get("key"):
            return ""
        if receipt.get("executions", 1) < self.state["repeat_limit"]:
            return ""
        self.replays += 1
        if self.replays >= 2:
            self.halted = ("تم منع تكرار إجراء سبق أن نجح. النتيجة محفوظة، لكن اكتمال بقية المهمة لم يُثبت. "
                           "آخر نتيجة: " + str(receipt.get("result") or "")[:600])
        return ("[Runtime receipt: this exact action already succeeded. It was NOT executed again. "
                "Use the result below; finish if it satisfies the request, otherwise do only the remaining work.]\n"
                + str(receipt.get("result") or ""))

    def observe(self, name, args, kind, text, meta, ok):
        if not ok or not successful(meta, text):
            self.last_failed = True
            return
        if progress_guard.is_observation(name, args, kind):
            return
        if name == "task_complete":
            pending = any(x.get("status") not in ("done", "completed") for x in self.session.todo
                          if isinstance(x, dict))
            if meta.get("completed") and meta.get("task_id") == self.session.active_task_id and \
                    self.state.get("receipt") and not pending and not self.last_failed and not self.session.goal:
                self._candidate = str(args.get("summary") or "تم إنجاز المهمة.")[:2000]
            return
        key = self._key(name, args, kind)
        # Metadata/checkpoints do not change the external state. A different
        # action (including navigation/tap) invalidates the previous receipt.
        if key or kind in ("edit", "run", "phone", "mcp"):
            previous = self.state.get("receipt") or {}
            count = previous.get("executions", 1) + 1 if key and key == previous.get("key") else 1
            self.state["receipt"] = {"key": key, "result": str(text)[:1400], "tool": name,
                                     "executions": count} if key else {}
            self.replays = 0
            self.last_failed = False
            self._persist()
        if name == "phone" and args.get("action") == "open_app" and self.target and \
                app_identity(args.get("name")) == self.target and meta.get("phone", {}).get("ok") is True:
            # Native Phone.openApp returns this only after startActivity succeeds.
            # It proves launching, not sending messages or any additional work.
            match = re.fullmatch(r"opened (.+)", str(text).strip(), re.I)
            if match and app_identity(match[1]) in (self.target, app_identity(args.get("name"))) and \
                    not getattr(self.session, "goal", "") and not any(
                    x.get("status") not in ("done", "completed") for x in self.session.todo if isinstance(x, dict)):
                self._candidate = "تم تنفيذ طلب فتح %s بنجاح." % match[1][:120]

    def answer(self):
        return self._candidate or str(self.state.get("terminal") or "")

    def clear_completion(self):
        self._candidate = ""
        self.state["terminal"] = ""
        self._persist()

    def finish(self, error=""):
        # Persist terminal state only AFTER verification, goals and stop hooks.
        self.state["terminal"] = "" if error else self.answer()
        self._persist()
