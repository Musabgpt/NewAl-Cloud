"""Patch exact Action #43 server with MusabAI's standalone Cloud Workspace API."""
from pathlib import Path
import json
import os
import re
import time

root = Path(__file__).resolve().parents[1]
server = root / "desktop" / "newal_code" / "server.py"
text = server.read_text(encoding="utf-8")
if "from pathlib import Path" not in text:
    text = text.replace("import queue\n", "import queue\nfrom pathlib import Path\n", 1)

anchor = '''            if path == "/api/cloud":
                from . import cloud
                return self._json({"tasks": cloud.listing(q.get("root") or None)})'''
insert = '''            if path == "/api/cloud/workspace":
                return self._json({"workspaces": _cloud_workspaces()})
            if path == "/api/connectors":
                return self._json(_connector_status())'''
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
            if path == "/api/connectors/start":
                cid = str(b.get("id") or "")
                cat = _connector_catalog().get(cid)
                if not cat:
                    return self._json({"error": "Connector requires official setup; no endpoint is configured for " + cid}, 400)
                if cid == "github":
                    try:
                        from . import github
                        a = github.account()
                        if a.get("connected"):
                            return self._json({"connected": True, "login": a.get("login","")})
                    except Exception:
                        pass
                return self._json({"connected": False, "available": True, "url": cat["url"],
                                   "message": "MCP OAuth endpoint is configured. Browser authorization must be completed by the MCP OAuth bridge; no token field is used."})
            if path == "/api/connectors/status":
                cid = str(q.get("id") or "")
                return self._json(_connector_status().get(cid) or {})
            if path == "/api/cloud" or path.startswith("/api/cloud/"):'''
if post_anchor not in text:
    raise SystemExit("POST cloud anchor changed; refusing to patch")
text = text.replace(post_anchor, post_insert, 1)

helpers = '''
# ------------------------------------------------------------------ standalone Cloud Session
def _cloud_root():
    base = Path(settings.HOME) / "cloud" / "workspaces"
    base.mkdir(parents=True, exist_ok=True)
    return base

def _safe_title(value):
    value = re.sub(r"[^A-Za-z0-9 _.-]+", " ", str(value or "")).strip()
    return re.sub(r"\\s+", " ", value)[:70] or "New cloud workspace"

def _create_cloud_workspace(title):
    wid = time.strftime("%Y%m%d-%H%M%S") + "-" + secrets.token_hex(4)
    d = _cloud_root() / wid
    d.mkdir(parents=True, exist_ok=False)
    (d / ".musabai-cloud").write_text(
        '{"version":1,"kind":"standalone-cloud-workspace","id":"%s","title":%s}\\n'
        % (wid, json.dumps(_safe_title(title), ensure_ascii=False)),
        encoding="utf-8")
    (d / "README.md").write_text(
        "# MusabAI Cloud Workspace\\n\\n"
        "This workspace is independent of Git and GitHub. "
        "Connect GitHub later only when you ask MusabAI to publish or sync it.\\n",
        encoding="utf-8")
    return {"id": wid, "root": str(d), "title": _safe_title(title), "cloud": True}

def _connector_catalog():
    return {
        "github": {"url": "https://api.githubcopilot.com/mcp/", "auth": "oauth"},
        "google-drive": {"url": "https://drivemcp.googleapis.com/mcp/v1", "auth": "oauth"},
        "gmail": {"url": "https://gmailmcp.googleapis.com/mcp/v1", "auth": "oauth"},
        "google-calendar": {"url": "https://calendarmcp.googleapis.com/mcp/v1", "auth": "oauth"},
        "google-docs": {"url": "https://docsmcp.googleapis.com/mcp/v1", "auth": "oauth"},
        "google-sheets": {"url": "https://sheetsmcp.googleapis.com/mcp/v1", "auth": "oauth"},
        "figma": {"url": "https://mcp.figma.com/mcp", "auth": "oauth"},
        "notion": {"url": "https://mcp.notion.com/mcp", "auth": "oauth"},
    }

def _connector_status():
    try:
        from . import github
        a = github.account()
        gh = bool(a.get("connected"))
    except Exception:
        gh = False
    catalog = _connector_catalog()
    ids = list(catalog) + [
        "gitlab","slack","discord","dropbox","onedrive","outlook","teams","trello",
        "linear","jira","asana","replit","kaggle","hugging-face","vercel","netlify",
        "firebase","supabase","sentry"
    ]
    out = {}
    for i in ids:
        configured = i in catalog
        out[i] = {"connected": gh if i == "github" else False,
                  "kind": "mcp-oauth" if configured else "oauth",
                  "configured": configured,
                  "available": configured}
    return out

def _cloud_workspaces():
    base = _cloud_root()
    out = []
    for d in sorted(base.iterdir(), reverse=True):
        if d.is_dir() and (d / ".musabai-cloud").exists():
            out.append({"id": d.name, "root": str(d)})
    return out

'''
anchor2="\ndef _changes_summary(s):\n"
if anchor2 not in text:
    raise SystemExit("helper anchor changed")
text = text.replace(anchor2, helpers + anchor2, 1)

old='''                return self._json({"id": s.id, "meta": s.meta()})'''
new='''                meta = s.meta()
                meta["cloud_workspace"] = str(meta.get("root") or "").startswith(str(_cloud_root()) + os.sep)
                return self._json({"id": s.id, "meta": meta})'''
if old not in text:
    raise SystemExit("session create return anchor changed")
text = text.replace(old, new, 1)

old2='''                return self._json({"meta": s.meta(), "events": s.events[-1500:], "busy": svc.busy(s.id),'''
new2='''                meta = s.meta()
                meta["cloud_workspace"] = str(meta.get("root") or "").startswith(str(_cloud_root()) + os.sep)
                return self._json({"meta": meta, "events": s.events[-1500:], "busy": svc.busy(s.id),'''
if old2 not in text:
    raise SystemExit("session GET anchor changed")
text = text.replace(old2, new2, 1)

server.write_text(text, encoding="utf-8")
print("patched", server)
