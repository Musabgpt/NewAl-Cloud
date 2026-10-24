"""A Facebook Page connected in the app (facebook_page.py, FacebookPage.java): facebook_page_post and
facebook_page_recent, offered while the Page is connected (lean mode too), and its card in Connections."""
import shutil


def apply(src, package, replace):
    for name in ("facebook_page.py", "ext_facebook_tests.py"):
        shutil.copyfile(src / name, package / name)
    ui = package / "ui"
    shutil.copyfile(src / "ext_facebook.js", ui / "ext_facebook.js")
    replace(ui / "index.html", '<script src="mcp_ui.js"></script>',
            '<script src="mcp_ui.js"></script>\n<script src="ext_facebook.js"></script>')

    replace(package / "tools.py", "_task_state.install()\n",
            "_task_state.install()\nfrom . import facebook_page as _facebook_page\n_facebook_page.install()\n")
    # its two tools are offered on the phone too, like GitHub's and Termux's
    replace(package / "lean.py", 'CONNECTOR_PREFIXES = ("github_", "termux_")',
            'CONNECTOR_PREFIXES = ("github_", "termux_", "facebook_page_")')

    with open(package / "claude_parity_tests.py", "a", encoding="utf-8") as f:
        f.write("\nfrom .ext_facebook_tests import FacebookTests  # noqa: E402,F401 - run with the parity tests in CI\n")
