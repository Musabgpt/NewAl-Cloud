"""Apply small, checked patches to the immutable Action #43 engine used by #125."""
from pathlib import Path
import json
import os
import shutil
import sys
import urllib.parse

SOURCE_SHA = "0bf36a3b3a813dbac424ee0c4dc6341f9e3fe0d3"


def replace(path, before, after):
    text = path.read_text()
    if text.count(before) != 1:
        raise SystemExit(f"Unsafe patch refused: {path.name}: expected exactly one anchor")
    path.write_text(text.replace(before, after, 1))


def apply(root):
    package = root / "desktop/newal_code"
    here = Path(__file__).resolve().parent
    shutil.copyfile(here / "runtime.py", package / "connectors.py")
    shutil.copyfile(here / "ui.js", package / "ui/connectors.js")
    shutil.copyfile(here / "ui.css", package / "ui/connectors.css")
    # Preview coexists with #125, including its optional legacy Termux engine.
    replace(package / "termux.py", 'PHONE_PORT = 8793', 'PHONE_PORT = int(os.environ.get("NEWAL_PHONE_PORT") or 8793)')
    replace(package / "termux.py", '    return SCRIPT.replace("@KEY@", _sh(key))', '    script = SCRIPT\n    if os.environ.get("NEWAL_TERMUX_PROFILE") == "preview":\n        script = script.replace(".newal-code", ".newal-code-preview").replace("newal-termux", "newal-termux-preview").replace(\'$PREFIX/bin/newal"\', \'$PREFIX/bin/newal-preview"\')\n        script = script.replace("export PYTHONPATH=", "export NEWAL_TERMUX_PROFILE=preview NEWAL_TERMUX_PORT=8798 NEWAL_PHONE_PORT=8796 PYTHONPATH=")\n    return script.replace("@KEY@", _sh(key))')
    replace(package / "tools.py", "# ------------------------------------------------------------------ tool sets\n", "# MUSAB_CONNECTORS_V1: register after Tool/registry definitions\nfrom . import connectors as _connectors\n\n# ------------------------------------------------------------------ tool sets\n")
    replace(package / "agent.py", "        return self._schemas\n", """        from . import connectors
        available = connectors.names()
        allowed = (self.agent_def or {}).get("tools")
        if allowed:
            available = [n for n in available if n in allowed]
        self.session.tool_names = [n for n in self.session.tool_names if n not in connectors.OPERATIONS] + available
        # Live connector state is checked on every request; existing MCP schemas remain intact.
        return [d for d in self._schemas if d["function"]["name"] not in connectors.OPERATIONS] + tools.schemas(available)
""")
    replace(package / "permissions.py", '    if kind == "mcp":\n', '''    if kind == "connector_write":
        if mode == "read-only":
            return Decision(DENY, "read-only mode: no changes to connected accounts")
        return Decision(ASK, "change connected account using %s" % tool)
    if kind == "mcp":
''')
    replace(package / "permissions.py", 'COMMAND_TOOLS = ("bash", "powershell")', 'COMMAND_TOOLS = ("bash", "powershell", "termux_exec")')
    replace(package / "server.py", '        q = self._query()\n        svc = self.service\n', '''        q = self._query()
        from . import connectors
        if connectors.route(self, "GET", path):
            return
        svc = self.service
''')
    replace(package / "server.py", '        b = self._body()\n        svc = self.service\n', '''        b = self._body()
        from . import connectors
        if connectors.route(self, "POST", path, b):
            return
        svc = self.service
''')
    replace(package / "ui/index.html", '<link rel="stylesheet" href="style.css">', '<link rel="stylesheet" href="style.css">\n<link rel="stylesheet" href="connectors.css">')
    replace(package / "ui/index.html", '<script src="app.js"></script>', '<script src="app.js"></script>\n<script src="connectors.js"></script>')
    # Surgical changes for independent workspace sessions; repository tasks remain a separate feature.
    replace(package / "ui/app.js", '    if (!root) return pickFolder(r => newThread(r));', '''    if (!root && pref("env") === "cloud") {
      const d = await api("/api/workspaces", { model: pref("model"), mode: pref("mode") });
      return openSession(d.id);
    }
    if (!root) return pickFolder(r => newThread(r));''')
    replace(package / "ui/app.js", '    if (!S.root) { await new Promise(res => pickFolder(r => { setRoot(r); res(); })); }\n    if (S.current) return S.current;', '''    if (pref("env") === "cloud") {
      const d = await api("/api/workspaces", { model: pref("model"), mode: pref("mode") });
      await openSession(d.id);
      return d.id;
    }
    if (!S.root) { await new Promise(res => pickFolder(r => { setRoot(r); res(); })); }
    if (S.current) return S.current;''')
    replace(package / "ui/app.js", '    if (!S.current && pref("env") === "cloud" && !text.startsWith("/")) return sendToCloud(text);\n', '')
    replace(package / "ui/app.js", '{ value: "cloud", title: "Cloud", sub: "On GitHub Actions, with the repository: review the diff here, apply it or open a pull request", checked: env === "cloud" }', '{ value: "cloud", title: "Independent workspace", sub: "Empty workspace on this device; the selected cloud model answers. No GitHub account required. Remote execution is not configured.", checked: env === "cloud" }')
    replace(package / "ui/app.js", '{ worktree: "Worktree", cloud: "Cloud" }', '{ worktree: "Worktree", cloud: "Workspace" }')
    replace(package / "ui/app.js", '    updatePickers();\n    renderEmpty();\n    $("#input").focus();\n', '    updatePickers();\n    renderEmpty();\n    $("#input").focus();\n    if (new URLSearchParams(location.search).get("connections") === "1") window.openMusabConnectors();\n')
    replace(package / "ui/index.html", '<span>Cloud tasks</span>', '<span>Repository tasks</span>')
    url = os.environ.get("MUSAB_CONNECTOR_BROKER_URL", "").rstrip("/")
    if url:
        parsed = urllib.parse.urlsplit(url)
        if parsed.scheme != "https" or not parsed.netloc or parsed.path or parsed.query or parsed.fragment or parsed.username:
            raise SystemExit("Connector broker must be an HTTPS origin")
    (root / "android-lite/app/src/main/assets/connectors.json").write_text(json.dumps({"broker_url": url}) + "\n")


if __name__ == "__main__":
    apply(Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve())
