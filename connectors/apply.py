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


def maybe_replace(path, before, after):
    """Keep the patch idempotent when an upstream engine already has a feature."""
    text = path.read_text()
    if before in text:
        path.write_text(text.replace(before, after, 1))


def apply(root):
    package = root / "desktop/newal_code"
    here = Path(__file__).resolve().parent
    shutil.copyfile(here / "runtime.py", package / "connectors.py")
    shutil.copyfile(here.parent / "desktop/autonomy/test_memory.py", package / "autonomy_tests.py")
    for name in ("documents", "evolution", "addons", "memory_api", "agent_policy", "workbench", "workbench_tests", "mcp_config", "mcp_config_tests", "mcp_bundles", "mcp_bundles_tests", "mcp_registry", "mcp_registry_tests", "browser_router", "browser_router_tests", "search_router", "search_router_tests", "document_engine", "document_engine_tests", "provider_pool", "provider_pool_tests", "provider_keys", "provider_keys_tests", "document_tests", "evolution_tests", "addon_tests", "memory_tests", "prompt_tests"):
        shutil.copyfile(here / (name + ".py"), package / (name + ".py"))
    shutil.copyfile(here / "agent_prompt.md", package / "agent_prompt.md")
    replace(package / "phone.py", '           "intent", "wait")', '           "intent", "wait", "screenshot", "install_apk", "notifications_read", "automation_start", "automation_stop", "automation_list", "automation_replay", "crash_reports")')
    replace(package / "phone.py", 'DOC = ("Use the Android phone this runs on: open apps and links, alarms, settings, and what is on the screen (screen "', 'DOC = ("Use the Android phone this runs on locally: read UI, screenshot, tap, type, swipe, launch apps, install an APK with Android confirmation, read optional notifications, record/replay workflows, and read MusabTestBridge crash/ANR reports. No Wi-Fi or MCP is needed. Use the Android phone this runs on: open apps and links, alarms, settings, and what is on the screen (screen "')
    replace(package / "phone.py", '        "(title, text); share (text); sms, call (number, text: the user sends); settings (page: wifi, bluetooth, "', '        "(title, text); share (text); sms, call (number, text: the user sends); screenshot; install_apk (path); notifications_read; "\n        "automation_start/stop/list/replay; crash_reports; settings (page: wifi, bluetooth, "')
    replace(package / "phone.py", '    "intent": {"type": "object"},', '    "intent": {"type": "object"},\n    "path": {"type": "string"},')
    import re
    phone_text = (package / "phone.py").read_text()
    phone_text, count = re.subn(r'    "action": \{"type": "string", "enum": list\(ACTIONS\), "description": \(.*?\)\},\n',
                                '    "action": {"type": "string", "enum": list(ACTIONS), "description": "local Android action"},\n', phone_text, count=1, flags=re.S)
    if count != 1:
        raise SystemExit("Unsafe patch refused: compact phone schema anchor missing")
    (package / "phone.py").write_text(phone_text)
    replace(package / "prompts.py", 'import platform\n', 'import platform\nfrom . import agent_policy\n')
    replace(package / "prompts.py", '    text = (LOCAL if local else SYSTEM).format(steps=steps, **environment("", shell))\n', '    text = agent_policy.profile() + "\\n\\nEnvironment: {os}; shell: {shell}.".format(**environment("", shell))\n    if phone:\n        text += "\\n\\n" + agent_policy.PHONE_GUIDANCE\n    if local:\n        text += "\\n\\n" + BREAKER_RULE.format(steps=steps)\n')
    replace(package / "agent.py", '    def system_prompt(self):\n        if not self.session.system:\n', '    def system_prompt(self):\n        from . import agent_policy\n        if not self.agent_def and agent_policy.stale_builtin(self.session.system):\n            self.session.system = ""\n        if not self.session.system:\n')
    replace(package / "agent.py", '        return [{"role": "system", "content": self.system_prompt()}]', '        from . import agent_policy\n        return [{"role": "system", "content": self.system_prompt() + agent_policy.runtime_context(self)}]')
    replace(package / "agent.py", '("text_delta", "reasoning_delta", "output", "tool_args")', '("text_delta", "reasoning_delta", "output", "tool_args", "terminal_output")')
    shutil.copyfile(here / "workspace.js", package / "ui/workspace.js")
    shutil.copyfile(here / "mcp_ui.js", package / "ui/mcp_ui.js")
    replace(package / "mcp.py", '    if root:\n', '    from . import mcp_config\n    add(mcp_config.configs(root))\n    if root:\n')
    replace(package / "mcp.py", '            cls = HttpServer if spec.get("url") else StdioServer\n', '            from . import mcp_config\n            cls = mcp_config.HttpServer if spec.get("_musab_managed") and spec.get("url") else mcp_config.StdioServer if spec.get("_musab_managed") else HttpServer if spec.get("url") else StdioServer\n')
    replace(package / "agent.py", '        if self._schemas is None:\n', '        from . import mcp_config\n        mcp_config.refresh_agent(self)\n        if self._schemas is None:\n')
    maybe_replace(package / "models.py", 'from . import settings, catalog, gguf, hardware, onetap, runtime, providers\n', 'from . import settings, catalog, gguf, hardware, onetap, runtime, providers\nfrom . import provider_pool\n')
    maybe_replace(package / "models.py", '        return self.provider.chat(self.model_name, messages, tools=tools, extra=extra, **kw)\n', '        return provider_pool.chat(self, messages, tools=tools, extra=extra, **kw)\n')
    models_text = (package / "models.py").read_text()
    if "from . import provider_pool" not in models_text:
        (package / "models.py").write_text("from . import provider_pool\n" + models_text)
    shutil.copyfile(here / "ui.js", package / "ui/connectors.js")
    shutil.copyfile(here / "ui.css", package / "ui/connectors.css")
    # Preview coexists with #125, including its optional legacy Termux engine.
    replace(package / "termux.py", 'PHONE_PORT = 8793', 'PHONE_PORT = int(os.environ.get("NEWAL_PHONE_PORT") or 8793)')
    replace(package / "termux.py", '    return SCRIPT.replace("@KEY@", _sh(key))', '    script = SCRIPT\n    if os.environ.get("NEWAL_TERMUX_PROFILE") == "preview":\n        script = script.replace(".newal-code", ".newal-code-preview").replace("newal-termux", "newal-termux-preview").replace(\'$PREFIX/bin/newal"\', \'$PREFIX/bin/newal-preview"\')\n        script = script.replace("export PYTHONPATH=", "export NEWAL_TERMUX_PROFILE=preview NEWAL_TERMUX_PORT=8798 NEWAL_PHONE_PORT=8796 PYTHONPATH=")\n    return script.replace("@KEY@", _sh(key))')
    replace(package / "tools.py", "# ------------------------------------------------------------------ tool sets\n", "# MUSAB_CONNECTORS_V1: register after Tool/registry definitions\nfrom . import connectors as _connectors\nfrom . import documents as _documents, evolution as _evolution\nfrom . import addons as _addons\nfrom . import browser_router as _browser_router\nfrom . import search_router as _search_router\nfrom . import document_engine as _document_engine\n_browser_router.install()\n_search_router.install()\n_document_engine.install()\n\n# ------------------------------------------------------------------ tool sets\n")
    replace(package / "tools.py", 'from . import addons as _addons\n', 'from . import addons as _addons\nfrom . import workbench as _workbench\n_workbench.install()\n')
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
    replace(package / "server.py", '        given = self._given_key()\n', '        if path == "/api/mcp-oauth/callback" and self.command == "GET":\n            return True\n        given = self._given_key()\n')
    replace(package / "server.py", '        q = self._query()\n        svc = self.service\n', '''        q = self._query()
        # Readiness must not run hardware probes, shell discovery or project scans.
        if path == "/api/health":
            return self._json({"ok": True})
        from . import connectors, documents, evolution, addons, memory_api, mcp_config, mcp_bundles, mcp_registry, browser_router, search_router, document_engine, provider_keys
        if mcp_config.route(self, "GET", path):
            return
        if mcp_bundles.route(self, "GET", path):
            return
        if mcp_registry.route(self, "GET", path):
            return
        if browser_router.route(self, "GET", path):
            return
        if search_router.route(self, "GET", path):
            return
        if document_engine.route(self, "GET", path):
            return
        if provider_keys.route(self, "GET", path):
            return
        if memory_api.route(self, "GET", path) or documents.route(self, "GET", path) or evolution.route(self, "GET", path) or addons.route(self, "GET", path):
            return
        if connectors.route(self, "GET", path):
            return
        svc = self.service
''')
    replace(package / "server.py", '        b = self._body()\n        svc = self.service\n', '''        b = self._body()
        from . import connectors, documents, evolution, addons, memory_api, mcp_config, mcp_bundles, mcp_registry, browser_router, search_router, document_engine, provider_keys
        if mcp_config.route(self, "POST", path, b):
            return
        if mcp_bundles.route(self, "POST", path, b):
            return
        if mcp_registry.route(self, "POST", path, b):
            return
        if browser_router.route(self, "POST", path, b):
            return
        if search_router.route(self, "POST", path, b):
            return
        if document_engine.route(self, "POST", path, b):
            return
        if provider_keys.route(self, "POST", path, b):
            return
        if memory_api.route(self, "POST", path, b) or documents.route(self, "POST", path, b) or evolution.route(self, "POST", path, b) or addons.route(self, "POST", path, b):
            return
        if connectors.route(self, "POST", path, b):
            return
        svc = self.service
''')
    replace(package / "ui/index.html", '<link rel="stylesheet" href="style.css">', '<link rel="stylesheet" href="style.css">\n<link rel="stylesheet" href="connectors.css">')
    replace(package / "ui/index.html", '<script src="app.js"></script>', '<script src="app.js"></script>\n<script src="connectors.js"></script>\n<script src="workspace.js"></script>\n<script src="mcp_ui.js"></script>')
    replace(package / "server.py", 'if x != "env"', 'if x not in ("env", "headers")')
    replace(package / "tools.py", '    names += ["memory_recall"]\n', '    names += ["memory_recall"] + _documents.NAMES + _evolution.NAMES + _addons.NAMES + _browser_router.NAMES + _search_router.NAMES + _document_engine.NAMES\n')
    replace(package / "ui/app.js", '    connectEvents();\n', '    window.NewAlWorkspaceSession = () => S.current;\n    connectEvents();\n')
    replace(package / "agent.py", '        parts.append(text)\n', '        parts.append("For document tasks use document_create/read/download and archive_pack/extract. Save a real file and report its path; do not claim a file exists without checking. For self-improvement use self_evolve, edit the isolated candidate, then self_evolve_verify. Never claim an untested candidate improved intelligence. Remember supported preferences with memory_learn.")\n        parts.append(text)\n')
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

