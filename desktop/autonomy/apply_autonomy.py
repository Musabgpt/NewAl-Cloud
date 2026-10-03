"""Apply the autonomous extension to an exact Action #43 checkout."""
from __future__ import annotations
import os
import sys

MARK = "# NEWAL_CLOUD_AUTONOMY_V1"


def patch_tools(path):
    text = open(path, encoding="utf-8").read()
    tool_mark = "# NEWAL_CLOUD_AUTONOMY_TOOLS_V1"
    if tool_mark in text:
        return
    needle = "from . import settings\n"
    if needle not in text:
        raise SystemExit("Action #43 tools.py import anchor changed; refusing an unsafe patch")
    text = text.replace(needle, needle + "from . import autonomy as _autonomy\n", 1)
    anchor = "# ------------------------------------------------------------------ tool sets\n"
    if anchor not in text:
        raise SystemExit("Action #43 tools.py tool-set anchor changed; refusing an unsafe patch")
    block = """# NEWAL_CLOUD_AUTONOMY_TOOLS_V1
@tool("memory_recall", "Recall durable lessons from previous work on this project.",
      {"query": _s("topic, error, or task to recall"), "limit": _i("maximum lessons")}, [], "read")
def t_memory_recall(ctx, query="", limit=12):
    rows = _autonomy.memory_for(ctx.root).recall(str(query or ""), int(limit or 12))
    if not rows:
        return "no durable lessons yet", {"items": 0}
    out = "\n".join("- %s: %s" % (r["topic"], r["lesson"]) for r in rows)
    return out, {"items": len(rows)}

@tool("self_evolve", "Verify a change to NewAl's own source on a candidate branch. It never force-pushes or overwrites a dirty repository.",
      {"goal": _s("what should improve"), "checks": {"type": "array", "items": {"type": "string"},
       "description": "build/test commands to run"}, "promote": _b("reserved for a future explicit promotion gate")}, ["goal"], "exec")
def t_self_evolve(ctx, goal, checks=None, promote=False):
    ev = getattr(ctx.agent, "evolution", None)
    if ev is None:
        raise ToolError("self-evolution is not configured; set NEWAL_SELF_REPO")
    result = ev.evolve(str(goal), checks or [], bool(promote))
    return json.dumps(result, ensure_ascii=False, indent=2), result

"""
    text = text.replace(anchor, block + anchor, 1)
    default = '    names = ["read", "edit", "write", "glob", "grep", "bash", "job", "todo", "task"]\n'
    if default not in text:
        raise SystemExit("Action #43 tools.py default tool set changed; refusing an unsafe patch")
    text = text.replace(default, default + '    names += ["memory_recall", "self_evolve"]\n', 1)
    open(path, "w", encoding="utf-8", newline="").write(text)

def main():
    if len(sys.argv) != 2:

        raise SystemExit("usage: apply_autonomy.py path/to/agent.py")
    path = os.path.abspath(sys.argv[1])
    text = open(path, encoding="utf-8").read()
    if MARK in text:
        raise SystemExit("already patched")
    needle = "from .session import Session\n"
    if needle not in text:
        raise SystemExit("Action #43 agent.py anchor changed; refusing an unsafe patch")
    text = text.replace(needle, needle + "from . import autonomy as _autonomy\n", 1)
    needle2 = "        self._context_lock = threading.Lock()\n"
    if needle2 not in text:
        raise SystemExit("Agent constructor anchor changed; refusing an unsafe patch")
    text = text.replace(
        needle2,
        needle2 + "        %s\n        self.memory = _autonomy.memory_for(session.root)\n"
        "        self.evolution = _autonomy.SelfEvolution(_autonomy.self_repo(), self.memory) "
        "if _autonomy.self_repo() else None\n" % MARK, 1)
    needle3 = "        self.emit({\"type\": \"turn_start\", \"turn\": s.turn, \"text\": text, \"model\": client.id, \"mode\": s.mode})\n"
    if needle3 not in text:
        raise SystemExit("turn_start anchor changed; refusing an unsafe patch")
    text = text.replace(
        needle3,
        needle3 + "        self.memory.episode(\"turn\", s.id, text, \"turn started\")\n"
        "        remembered = self.memory.recall(text, 8)\n"
        "        if remembered:\n"
        "            self.emit({\"type\":\"memory\",\"items\":remembered})\n", 1)
    needle4 = "        finally:\n            if self.depth == 0 and error == \"interrupted\":\n"
    if needle4 not in text:
        raise SystemExit("turn finalization anchor changed; refusing an unsafe patch")
    text = text.replace(
        needle4,
        "        finally:\n"
        "            if error:\n"
        "                self.memory.episode(\"failure\", s.id, text, answer, error)\n"
        "                if self.last_error:\n"
        "                    self.memory.learn(\"failure\", self.last_error, answer)\n"
        "            else:\n"
        "                self.memory.episode(\"success\", s.id, text, answer)\n"
        "            if self.depth == 0 and error == \"interrupted\":\n", 1)
    open(path, "w", encoding="utf-8", newline="").write(text)
    tools_path = os.path.join(os.path.dirname(path), "tools.py")
    patch_tools(tools_path)
    print("autonomy patch applied")


if __name__ == "__main__":
    main()
