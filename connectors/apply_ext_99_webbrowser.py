"""The agent's own browser: Firefox's engine (GeckoView) inside the app, never on screen (HeadlessBrowser.java and the
page reader in assets/musab_browser). This installs the agent's tools (web_browser.py: browser_open, browser_read,
browser_click, browser_type, browser_scroll, browser_back), offers them on the phone (lean.py lists them), teaches them
in the phone prompt, and shows each browser step in the chat as a card: what was done and on which page."""
import shutil


def apply(src, package, replace):
    for name in ("web_browser.py", "ext_web_browser_tests.py"):
        shutil.copyfile(src / name, package / name)

    tl = package / "tools.py"
    replace(tl, "_code_check.install()\n",
            "_code_check.install()\nfrom . import web_browser as _web_browser\n_web_browser.install()\n")
    # offered with the phone: the browser lives in the app (the lean set on the phone lists them too)
    replace(tl, "        names += _phone_ext.NAMES + _phone_fast.NAMES\n",
            "        names += _phone_ext.NAMES + _phone_fast.NAMES\n        names += _web_browser.NAMES\n")

    # the phone prompt (agent_prompt_lean.md) now teaches the browser: threads pick the new one up
    replace(package / "agent_policy.py", "MARKER = 'MusabAI behavior profile v11'",
            "MARKER = 'MusabAI behavior profile v12'")

    # the chat: each browser step is a card (verb, then the page and what was done on it), its body the page read;
    # what was typed is not shown on the card (it may be a password)
    app = package / "ui/app.js"
    replace(app, 'notebook_edit: "Edited notebook" };',
            'notebook_edit: "Edited notebook", browser_open: "Browsed", browser_read: "Read the page", '
            'browser_click: "Clicked", browser_type: "Typed", browser_scroll: "Scrolled", browser_back: "Went back" };')
    replace(app, '    if (name === "web_fetch") return esc(a.url || "");\n',
            '    if (name === "web_fetch") return esc(a.url || "");\n'
            '    if (name.startsWith("browser_")) return esc(name === "browser_open" ? a.url || ""\n'
            '      : name === "browser_click" || name === "browser_type" ? (a.item ? "[" + a.item + "]" : "")\n'
            '      : name === "browser_scroll" ? a.direction || "down" : "");\n')
    replace(app, '        if (!ev.ok && !ev.denied && rec.kind !== "bash") {\n',
            '        if (String(rec.kind || "").startsWith("browser_") && ev.ok && m.browser && m.browser.url) {\n'
            '          // the page it ended on, and what was clicked or typed into there\n'
            '          const w = it.querySelector(".what");\n'
            '          const did = String(m.browser.did || "").replace(/^(clicked|typed into) \\[\\d+\\] ?/, "");\n'
            '          const page = String(m.browser.title || m.browser.url.replace(/^https?:\\/\\//, "")).slice(0, 90);\n'
            '          w.textContent = (did ? did + " · " : "") + page;\n'
            '          w.title = m.browser.url;\n'
            '        }\n'
            '        if (!ev.ok && !ev.denied && rec.kind !== "bash") {\n')
    replace(package / "ui/i18n.js", '    "Used the phone": "استخدم الهاتف",\n',
            '    "Used the phone": "استخدم الهاتف",\n'
            '    "Browsed": "تصفّح",\n'
            '    "Read the page": "قرأ الصفحة",\n'
            '    "Clicked": "ضغط",\n'
            '    "Typed": "كتب في",\n'
            '    "Scrolled": "مرّر",\n'
            '    "Went back": "رجع",\n')

    with open(package / "claude_parity_tests.py", "a", encoding="utf-8") as f:
        f.write("\nfrom .ext_web_browser_tests import WebBrowserTests  # noqa: E402,F401 - run with the parity tests\n")
