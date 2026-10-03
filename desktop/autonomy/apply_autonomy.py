"""Apply the autonomous extension to an exact Action #43 checkout."""
from __future__ import annotations
import os
import sys

MARK = "# NEWAL_CLOUD_AUTONOMY_V1"


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
    print("autonomy patch applied")


if __name__ == "__main__":
    main()
