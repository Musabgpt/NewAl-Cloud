"""The phone by sight and several steps in one call (phone_sight.py): screen_tap and phone_steps, offered on the phone
(lean mode too) and kept in every request's core tools."""
import shutil


def apply(src, package, replace):
    for name in ("phone_sight.py", "ext_sight_tests.py"):
        shutil.copyfile(src / name, package / name)

    tl = package / "tools.py"
    replace(tl, "from . import phone_fast as _phone_fast\n_phone_fast.install()\n",
            "from . import phone_fast as _phone_fast\n_phone_fast.install()\n"
            "from . import phone_sight as _phone_sight\n_phone_sight.install()\n")
    replace(tl, "        names += _phone_ext.NAMES + _phone_fast.NAMES\n",
            "        names += _phone_ext.NAMES + _phone_fast.NAMES + _phone_sight.NAMES\n")
    replace(package / "lean.py", '    "web_search", "web_fetch",\n',
            '    "web_search", "web_fetch",\n    "screen_tap", "phone_steps",\n')
    replace(package / "claude_parity.py", '"screen_look", "android_test_app", ',
            '"screen_look", "android_test_app", "screen_tap", "phone_steps", ')

    with open(package / "claude_parity_tests.py", "a", encoding="utf-8") as f:
        f.write("\nfrom .ext_sight_tests import SightTests  # noqa: E402,F401 - run with the parity tests in CI\n")
