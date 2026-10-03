"""Patch exact Action #43 server with MusabAI's standalone Cloud Workspace API.

This deliberately does not alter Action #43's repository-backed Cloud Tasks.
It adds a separate first-class session workspace that uses the configured cloud
model and has no Git/GitHub prerequisite.
"""
from pathlib import Path
import re
import time
import uuid

root = Path(__file__).resolve().parents[1]
server = root / "desktop" / "newal_code" / "server.py"
text = server.read_text(encoding="utf-8")

# Add the route before the existing repository-backed /api/cloud route.
anchor = '''            if path == "/api/cloud":
                from . import cloud
                return self._json({"tasks": cloud.listing(q.get("root") or None)})'''
insert = '''            if path == "/api/cloud/workspace":
                return self._json({"workspaces": _cloud_workspaces()})'''
if anchor not in text:
    raise SystemExit("GET cloud anchor changed; refusing to patch")
text = text.replace(anchor, insert + "\n" + anchor, 1)

post_anchor = '''            if path == "/api/models/add":
                mid = b.pop("id", "") or b.get("model", "")
                if not mid:
                    return self._json({"error": "id needed"}, 400)
                cur = settings.user().get("models") or {}
                cur[mid] = {k: v for k, v in b.items() if v not in ("", None)}
                settings.save({"models": cur})
                return self._json({"ok": True, "id": mid})
            if path == "/api/cloud" or path.startswith("/api/cloud/"):'''
post_insert = '''            if path == "/api/models/add":
                mid = b.pop("id", "") or b.get("model", "")
                if not mid:
                    return self._json({"error": "id needed"}, 400)
                cur = settings.user().get("models") or {}
                cur[mid] = {k: v for k, v in b.items() if v not in ("", None)}
                settings.save({"models": cur})
                return self._json({"ok": True, "id": mid})
            if path == "/api/cloud/workspace":
                return self._json(_create_cloud_workspace(b.get("title") or "New cloud workspace"))
            if path == "/api/cloud" or path.startswith("/api/cloud/"):'''
if post_anchor not in text:
    raise SystemExit("POST cloud anchor changed; refusing to patch")
text=text.replace(post_anchor,post_insert,1)

helpers = r'''

# ------------------------------------------------------------------ standalone Cloud Session
def _cloud_root():
    base = Path(settings.HOME) / "cloud" / "workspaces"
    base.mkdir(parents=True, exist_ok=True)
    return base

def _safe_title(value):
    value = re.sub(r"[^A-Za-z0-9 _.-]+", " ", str(value or "")).strip()
    return re.sub(r"\s+", " ", value)[:70] or "New cloud workspace"

def _create_cloud_workspace(title):
    wid = time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:8]
    d = _cloud_root() / wid
    d.mkdir(parents=True, exist_ok=False)
    (d / ".musabai-cloud").write_text(
        '{"version":1,"kind":"standalone-cloud-workspace","id":"%s","title":%s}
'
        % (wid, json.dumps(_safe_title(title), ensure_ascii=False)),
        encoding="utf-8")
    (d / "README.md").write_text(
        "# MusabAI Cloud Workspace

"
        "This workspace is independent of Git and GitHub. "
        "Connect GitHub later only when you ask MusabAI to publish or sync it.
",
        encoding="utf-8")
    return {"id": wid, "root": str(d), "title": _safe_title(title), "cloud": True}

def _cloud_workspaces():
    base = _cloud_root()
    out = []
    for d in sorted(base.iterdir(), reverse=True):
        if d.is_dir():
            marker = d / ".musabai-cloud"
            if marker.exists():
                out.append({"id": d.name, "root": str(d)})
    return out
'''
# Insert helpers immediately before _changes_summary, which is stable in Action #43.
anchor2="
def _changes_summary(s):
"
if anchor2 not in text: raise SystemExit("helper anchor changed")
text=text.replace(anchor2,helpers+anchor2,1)

# Mark returned session metadata as cloud_workspace when its root is under the managed cloud workspace dir.
old='''                return self._json({"id": s.id, "meta": s.meta()})'''
new='''                meta = s.meta()
                meta["cloud_workspace"] = str(meta.get("root") or "").startswith(str(_cloud_root()) + os.sep)
                return self._json({"id": s.id, "meta": meta})'''
if old not in text: raise SystemExit("session create return anchor changed")
text=text.replace(old,new,1)

# Also expose the marker on GET session so the UI survives reload.
old2='''                return self._json({"meta": s.meta(), "events": s.events[-1500:], "busy": svc.busy(s.id),'''
new2='''                meta = s.meta()
                meta["cloud_workspace"] = str(meta.get("root") or "").startswith(str(_cloud_root()) + os.sep)
                return self._json({"meta": meta, "events": s.events[-1500:], "busy": svc.busy(s.id),'''
if old2 not in text: raise SystemExit("session GET anchor changed")
text=text.replace(old2,new2,1)

server.write_text(text, encoding="utf-8")
print("patched", server)
