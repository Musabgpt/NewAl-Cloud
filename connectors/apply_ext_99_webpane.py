"""The browser in the chat: MusabAI's own browser (GeckoView, Firefox's engine) in a pane above the conversation,
which the agent opens and reads (browser_open, browser_read, browser_close) while the user watches and can use it too.
The app's side is android-lite (BrowserPane.java, the page reader in assets/musab_browser); this installs the agent's
tools (browser_pane.py), offers them on the phone (lean.py lists them), and adds the globe button (browser_ui.js)."""
import shutil


def apply(src, package, replace):
    for name in ("browser_pane.py", "ext_browser_tests.py"):
        shutil.copyfile(src / name, package / name)
    shutil.copyfile(src / "browser_ui.js", package / "ui" / "browser_ui.js")

    tl = package / "tools.py"
    replace(tl, "_code_check.install()\n",
            "_code_check.install()\nfrom . import browser_pane as _browser_pane\n_browser_pane.install()\n")
    # offered with the phone: the pane lives in the app (the lean set on the phone lists them too)
    replace(tl, "        names += _phone_ext.NAMES + _phone_fast.NAMES\n",
            "        names += _phone_ext.NAMES + _phone_fast.NAMES\n        names += _browser_pane.NAMES\n")

    # the phone prompt (agent_prompt_lean.md) now teaches the pane: threads pick the new one up
    replace(package / "agent_policy.py", "MARKER = 'MusabAI behavior profile v11'",
            "MARKER = 'MusabAI behavior profile v12'")

    index = package / "ui/index.html"
    replace(index, '<script src="lean_ui.js"></script>\n',
            '<script src="lean_ui.js"></script>\n<script src="browser_ui.js"></script>\n')

    with open(package / "claude_parity_tests.py", "a", encoding="utf-8") as f:
        f.write("\nfrom .ext_browser_tests import BrowserPaneTests  # noqa: E402,F401 - run with the parity tests in CI\n")
