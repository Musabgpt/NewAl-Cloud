"""The phone by sight and several steps in one call (phone_sight.py): screen_tap and phone_steps. Not in lean mode's
set (the phone's default): every tool there goes with every request, and these two added 1.7k characters to each;
settings "lean": false offers them."""
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

    with open(package / "claude_parity_tests.py", "a", encoding="utf-8") as f:
        f.write("\nfrom .ext_sight_tests import SightTests  # noqa: E402,F401 - run with the parity tests in CI\n")
