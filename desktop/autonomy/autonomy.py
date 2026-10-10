"""Persistent memory and safe self-evolution for NewAl-Cloud.

This module is deliberately independent of the Action #43 agent loop. It stores
durable, local evidence and gives the agent a controlled path for evolving its
own source without ever replacing a known-good revision in place.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import subprocess
import threading
import time


def _clip(value, limit=8000):
    value = str(value or "")
    return value if len(value) <= limit else value[:limit] + "\n…"


def _safe_text(value, limit=8000):
    value = re.sub(r"(?i)(authorization\s*:\s*bearer\s+)[^\s]+", r"\1[redacted]", str(value or ""))
    value = re.sub(r"(?i)(api[_-]?key|token|password|secret)\s*[=:]\s*[^\s,;]+", r"\1=[redacted]", value)
    return _clip(value, limit)


class MemoryStore:
    """SQLite/WAL memory which survives app restarts and is safe for concurrent workers."""

    def __init__(self, root: str):
        self.root = os.path.abspath(root)
        base = os.environ.get("NEWAL_MEMORY_HOME") or os.path.join(
            os.environ.get("NEWAL_CODE_HOME") or os.path.expanduser("~/.newal-code"), "memory")
        os.makedirs(base, exist_ok=True)
        digest = hashlib.sha256(self.root.encode("utf-8")).hexdigest()[:16]
        self.path = os.path.join(base, digest + ".sqlite3")
        self.lock = threading.RLock()
        self.db = sqlite3.connect(self.path, check_same_thread=False, timeout=30)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=NORMAL")
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.executescript("""
        CREATE TABLE IF NOT EXISTS episodes(
          id INTEGER PRIMARY KEY, ts REAL NOT NULL, kind TEXT NOT NULL,
          session_id TEXT, task TEXT, summary TEXT, error TEXT, evidence TEXT
        );
        CREATE TABLE IF NOT EXISTS learnings(
          id INTEGER PRIMARY KEY, ts REAL NOT NULL, topic TEXT NOT NULL,
          lesson TEXT NOT NULL, evidence TEXT, hits INTEGER NOT NULL DEFAULT 0,
          last_used REAL
        );
        CREATE TABLE IF NOT EXISTS mutations(
          id INTEGER PRIMARY KEY, ts REAL NOT NULL, repo TEXT NOT NULL,
          base_ref TEXT, candidate_ref TEXT, goal TEXT, checks TEXT,
          result TEXT, promoted INTEGER NOT NULL DEFAULT 0
        );
        CREATE INDEX IF NOT EXISTS idx_learnings_topic ON learnings(topic);
        CREATE INDEX IF NOT EXISTS idx_episodes_task ON episodes(task);
        """)
        self.db.commit()

    def episode(self, kind, session_id="", task="", summary="", error="", evidence=""):
        with self.lock:
            self.db.execute(
                "INSERT INTO episodes(ts,kind,session_id,task,summary,error,evidence) VALUES(?,?,?,?,?,?,?)",
                (time.time(), kind, str(session_id), _safe_text(task), _safe_text(summary),
                 _safe_text(error), _safe_text(evidence)))
            self.db.commit()

    def learn(self, topic, lesson, evidence=""):
        topic = _safe_text(topic, 240)
        lesson = _safe_text(lesson, 4000)
        if not topic or not lesson:
            return
        with self.lock:
            row = self.db.execute(
                "SELECT id FROM learnings WHERE topic=? AND lesson=?", (topic, lesson)).fetchone()
            if row:
                self.db.execute("UPDATE learnings SET hits=hits+1,last_used=? WHERE id=?",
                                (time.time(), row[0]))
            else:
                self.db.execute(
                    "INSERT INTO learnings(ts,topic,lesson,evidence,hits,last_used) VALUES(?,?,?,?,1,?)",
                    (time.time(), topic, lesson, _safe_text(evidence), time.time()))
            self.db.commit()

    def recall(self, query="", limit=12):
        terms = [t.lower() for t in re.findall(r"[A-Za-z0-9_\-]{3,}", query or "")[:8]]
        with self.lock:
            rows = self.db.execute(
                "SELECT topic,lesson,evidence,hits,last_used FROM learnings "
                "ORDER BY hits DESC,last_used DESC,ts DESC LIMIT 200").fetchall()
        if terms:
            rows = [r for r in rows if any(t in (r[0] + " " + r[1]).lower() for t in terms)] or rows
        return [{"topic":r[0],"lesson":r[1],"evidence":r[2],"hits":r[3],"last_used":r[4]}
                for r in rows[:max(1, min(int(limit), 50))]]

    def recent_failures(self, limit=10):
        with self.lock:
            rows = self.db.execute(
                "SELECT ts,task,error,evidence FROM episodes WHERE kind='failure' "
                "ORDER BY ts DESC LIMIT ?", (max(1, min(int(limit), 50)),)).fetchall()
        return [{"ts":r[0],"task":r[1],"error":r[2],"evidence":r[3]} for r in rows]

    def close(self):
        with self.lock:
            self.db.close()


class SelfEvolution:
    """Safe candidate-branch evolution of the agent's own source repository."""

    def __init__(self, repo: str, memory: MemoryStore | None = None):
        self.repo = os.path.abspath(repo)
        self.memory = memory

    def _git(self, *args):
        p = subprocess.run(["git", *args], cwd=self.repo, text=True,
                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                           env={**os.environ, "GIT_TERMINAL_PROMPT":"0"}, timeout=120)
        return p.returncode, p.stdout.strip()

    def status(self):
        code, out = self._git("status", "--porcelain=v1")
        return {"clean": code == 0 and not out, "output": out, "code": code}

    def head(self):
        code, out = self._git("rev-parse", "HEAD")
        return out if code == 0 else ""

    def evolve(self, goal, checks, promote=False):
        goal = _safe_text(goal, 1000)
        checks = [str(x).strip() for x in (checks or []) if str(x).strip()]
        state = self.status()
        if not state["clean"]:
            raise RuntimeError("self-evolution requires a clean self-repository; refusing to overwrite local work")
        base = self.head()
        if not base:
            raise RuntimeError("cannot resolve self repository HEAD")
        suffix = hashlib.sha256((goal + str(time.time())).encode()).hexdigest()[:10]
        branch = "newal/self-evolve-" + suffix
        code, out = self._git("switch", "-c", branch, base)
        if code:
            raise RuntimeError(out or "cannot create candidate branch")
        results = []
        ok = True
        for command in checks:
            started = time.time()
            p = subprocess.run(command, cwd=self.repo, shell=True, text=True,
                               stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                               env={**os.environ, "GIT_TERMINAL_PROMPT":"0"}, timeout=1800)
            result = {"command":command,"exit":p.returncode,
                      "seconds":round(time.time()-started,2),"output":_clip(p.stdout,12000)}
            results.append(result)
            if p.returncode != 0:
                ok = False
                break
        code, diff = self._git("diff", "--check")
        ok = ok and code == 0
        results.append({"command":"git diff --check","exit":code,"output":_clip(diff,4000)})
        if self.memory:
            self.memory.db.execute(
                "INSERT INTO mutations(ts,repo,base_ref,candidate_ref,goal,checks,result,promoted) "
                "VALUES(?,?,?,?,?,?,?,?)",
                (time.time(), self.repo, base, branch, goal, json.dumps(results, ensure_ascii=False),
                 "passed" if ok else "failed", 0))
            self.memory.db.commit()
        return {"ok":ok,"base":base,"candidate":branch,"promoted":False,"checks":results}


def memory_for(root):
    return MemoryStore(root)


def self_repo():
    return os.environ.get("NEWAL_SELF_REPO", "").strip()
