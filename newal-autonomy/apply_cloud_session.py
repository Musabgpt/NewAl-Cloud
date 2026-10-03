"""Patch exact Action #43 server with a standalone Cloud Session and disable the legacy GitHub Actions cloud-task path."""
from pathlib import Path
import json
import os
import re
import secrets
import time

root = Path(__file__).resolve().parents[1]
server = root / "desktop" / "newal_code" / "server.py"
text = server.read_text(encoding="utf-8")

if "from pathlib import Path" not in text:
    text = text.replace("import queue\n", "import queue\nfrom pathlib import Path\n", 1)

# Remove the legacy POST /api/cloud submission implementation. Cloud Session is never repository-backed.
legacy = '''            if path == "/api/cloud" or path.startswith("/api/cloud/"):
                return self._json(*_cloud_post(path, b))'''
replacement = '''            if path == "/api/cloud":
                # Compatibility endpoint: old clients must enter the standalone Cloud Session,
                # never the legacy GitHub Actions cloud-task implementation.
                title = str(b.get("title") or "New cloud workspace")
                task = str(b.get("task") or "").strip()
                ws = _create_cloud_workspace(title)
                s = svc.create(ws["root"], model="kilo-auto/free", mode=b.get("mode") or "auto-edit",
                               worktree=False)
                svc.warm(s.id)
                meta = s.meta()
                meta["cloud_workspace"] = True
                result = {"id": s.id, "root": ws["root"], "workspace": ws, "meta": meta}
                if task:
                    result["send"] = svc.send(s.id, task, images=b.get("images") or None,
                                              lang=str(b.get("lang") or ""))
                return self._json(result)
            if path.startswith("/api/cloud/"):
                return self._json({"error": "The legacy repository-backed Cloud task API is disabled. "
                                            "Use Cloud Session; GitHub is optional."}, 410)'''
if legacy not in text:
    raise SystemExit("legacy POST /api/cloud anchor not found; refusing to patch")
text = text.replace(legacy, replacement, 1)

# Make every session explicitly report whether it is standalone Cloud.
old = '''                return self._json({"id": s.id, "meta": s.meta()})'''
new = '''                meta = s.meta()
                meta["cloud_workspace"] = str(meta.get("root") or "").startswith(str(_cloud_root()) + os.sep)
                return self._json({"id": s.id, "meta": meta})'''
if old in text:
    text = text.replace(old, new, 1)

old = '''                return self._json({"meta": s.meta(), "events": s.events[-1500:], "busy": svc.busy(s.id),'''
new = '''                meta = s.meta()
                meta["cloud_workspace"] = str(meta.get("root") or "").startswith(str(_cloud_root()) + os.sep)
                return self._json({"meta": meta, "events": s.events[-1500:], "busy": svc.busy(s.id),'''
if old in text:
    text = text.replace(old, new, 1)

# Standalone Cloud helpers.
if "def _cloud_root():" not in text:
    helpers = r'''
# ------------------------------------------------------------------ MusabAI standalone Cloud Session
def _cloud_root():
    base = Path(settings.HOME) / "cloud" / "workspaces"
    base.mkdir(parents=True, exist_ok=True)
    return base

def _safe_title(value):
    value = re.sub(r"[^A-Za-z0-9 _.-]+", " ", str(value or "")).strip()
    return re.sub(r"\s+", " ", value)[:70] or "New cloud workspace"

def _create_cloud_workspace(title):
    wid = time.strftime("%Y%m%d-%H%M%S") + "-" + secrets.token_hex(4)
    d = _cloud_root() / wid
    d.mkdir(parents=True, exist_ok=False)
    (d / ".musabai-cloud").write_text(
        '{"version":1,"kind":"standalone-cloud-workspace","id":"%s","title":%s}\n'
        % (wid, json.dumps(_safe_title(title), ensure_ascii=False)), encoding="utf-8")
    (d / "README.md").write_text(
        "# MusabAI Cloud Workspace\n\n"
        "Independent workspace. GitHub and Git are optional and only used when explicitly requested.\n",
        encoding="utf-8")
    return {"id": wid, "root": str(d), "title": _safe_title(title), "cloud": True}

def _cloud_workspaces():
    base = _cloud_root()
    return [{"id": d.name, "root": str(d)} for d in sorted(base.iterdir(), reverse=True)
            if d.is_dir() and (d / ".musabai-cloud").exists()]

'''
    anchor = '''
def _changes_summary(s):
'''
    if anchor not in text:
        raise SystemExit("helper anchor not found")
    text = text.replace(anchor, helpers + anchor, 1)

# Ensure GET workspace exists even if older patch shape is present.
if 'if path == "/api/cloud/workspace":' not in text:
    anchor = '''            if path == "/api/cloud":
                from . import cloud'''
    if anchor not in text:
        raise SystemExit("GET cloud anchor not found")
    text = text.replace(anchor, '''            if path == "/api/cloud/workspace":
                return self._json({"workspaces": _cloud_workspaces()})
            if path == "/api/cloud":
                from . import cloud''', 1)

server.write_text(text, encoding="utf-8")
print("patched", server)
