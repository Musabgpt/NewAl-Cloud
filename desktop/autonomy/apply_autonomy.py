"""Apply the autonomous layer to an exact Action #43 checkout.

All patches are anchor-checked. If upstream Action #43 changes, this script fails
closed rather than silently changing the agent.
"""
from __future__ import annotations
import os
import sys

MARK = "# NEWAL_CLOUD_AUTONOMY_V1"


def patch_tools(path):
    text = open(path, encoding="utf-8").read()
    if MARK + "_TOOLS" in text:
        return
    needle = "from . import settings\n"
    anchor = "# ------------------------------------------------------------------ tool sets\n"
    default = '    names = ["read", "edit", "write", "glob", "grep", "bash", "job", "todo", "task"]\n'
    for x, msg in ((needle, "tools import anchor"), (anchor, "tools section anchor"), (default, "default tool set anchor")):
        if x not in text:
            raise SystemExit("Action #43 tools.py %s changed; refusing unsafe patch" % msg)

    text = text.replace(needle, needle + "from . import autonomy as _autonomy\n", 1)
    block = '''# NEWAL_CLOUD_AUTONOMY_V1_TOOLS
@tool("memory_recall", "Recall durable lessons from previous work on this project.",
      {"query": _s("topic, error, or task to recall"), "limit": _i("maximum lessons")}, [], "read")
def t_memory_recall(ctx, query="", limit=12):
    store = _autonomy.memory_for(ctx.root)
    rows = store.recall(str(query or ""), int(limit or 12))
    if not rows:
        return "no durable lessons yet", {"items": 0}
    return "\\n".join("- %s: %s" % (r["topic"], r["lesson"]) for r in rows), {"items": len(rows)}

@tool("self_evolve", "Create and verify a candidate branch for improving NewAl itself; never force-pushes.",
      {"goal": _s("what should improve"),
       "checks": {"type": "array", "items": {"type": "string"}, "description": "build/test commands"}}, ["goal"], "exec")
def t_self_evolve(ctx, goal, checks=None):
    ev = getattr(ctx.agent, "evolution", None)
    if ev is None:
        raise ToolError("self-evolution is not configured")
    result = ev.evolve(str(goal), checks or [])
    return json.dumps(result, ensure_ascii=False, indent=2), result

'''
    text = text.replace(anchor, block + anchor, 1)
    text = text.replace(default, default + '    names += ["memory_recall", "self_evolve"]\n', 1)
    open(path, "w", encoding="utf-8", newline="").write(text)


def main():
    if len(sys.argv) != 2:
        raise SystemExit("usage: apply_autonomy.py path/to/agent.py")
    path = os.path.abspath(sys.argv[1])
    text = open(path, encoding="utf-8").read()
    if MARK in text:
        raise SystemExit("already patched")

    imp = "from .session import Session\n"
    ctor = "        self.lock = threading.Lock()\n"
    turn = '        self.emit({"type": "turn_start", "turn": s.turn, "text": text, "model": client.id, "mode": s.mode})\n'
    final = "        finally:\n            if self.depth == 0 and error == \"interrupted\":\n"
    user = "        parts += extra_context\n        parts.append(text)\n"

    for x, msg in ((imp,"import anchor"),(ctor,"constructor anchor"),(turn,"turn anchor"),(final,"finalization anchor"),(user,"user-content anchor")):
        if x not in text:
            raise SystemExit("Action #43 agent.py %s changed; refusing unsafe patch" % msg)

    text = text.replace(imp, imp + "from . import autonomy as _autonomy\n", 1)
    text = text.replace(
        ctor,
        ctor + "        %s\n        self.memory = _autonomy.memory_for(session.root)\n"
        "        self.evolution = _autonomy.SelfEvolution(_autonomy.self_repo(), self.memory) "
        "if _autonomy.self_repo() else None\n" % MARK, 1)
    text = text.replace(
        turn,
        turn + '        self.memory.episode("turn", s.id, text, "turn started")\n', 1)
    text = text.replace(
        final,
        "        finally:\n"
        "            if error:\n"
        "                self.memory.episode(\"failure\", s.id, text, answer, error)\n"
        "                if self.last_error:\n"
        "                    self.memory.learn(\"failure\", self.last_error, answer)\n"
        "            else:\n"
        "                self.memory.episode(\"success\", s.id, text, answer)\n"
        "            if self.depth == 0 and error == \"interrupted\":\n", 1)
    text = text.replace(
        user,
        "        parts += extra_context\n"
        "        learned = self.memory.recall(text, 4)\n"
        "        if learned:\n"
        "            parts.append(\"<learned-memory>\\\\n\" + \"\\\\n\".join(\"- %s: %s\" % (x[\"topic\"], x[\"lesson\"]) for x in learned) + \"\\\\n</learned-memory>\")\n"
        "        parts.append(text)\n", 1)

    open(path, "w", encoding="utf-8", newline="").write(text)
    patch_tools(os.path.join(os.path.dirname(path), "tools.py"))
    print("autonomy patch applied")


if __name__ == "__main__":
    main()
