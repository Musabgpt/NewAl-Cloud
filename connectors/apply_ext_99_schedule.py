"""Scheduled tasks and the proactive assistant (schedule.py): the schedule_task tool, /schedule and /duet, the Tasks
panel, and the clock that runs them (Android wakes the engine at a task's time)."""
import shutil


def apply(src, package, replace):
    for name in ("schedule.py", "ext_schedule_tests.py"):
        shutil.copyfile(src / name, package / name)
    ui = package / "ui"
    shutil.copyfile(src / "ext_schedule.js", ui / "ext_schedule.js")
    replace(ui / "index.html", '<script src="ext_fleet.js"></script>',
            '<script src="ext_fleet.js"></script>\n<script src="ext_schedule.js"></script>')

    tl = package / "tools.py"
    replace(tl, "_gh_monitor.install()\n",
            "_gh_monitor.install()\nfrom . import schedule as _schedule\n_schedule.install()\n")
    replace(tl, " + _fleet.NAMES + _gh_monitor.NAMES\n", " + _fleet.NAMES + _gh_monitor.NAMES + _schedule.NAMES\n")
    replace(package / "lean.py", '    "phone", "screen_look", "phone_routine",\n',
            '    "phone", "screen_look", "phone_routine",\n    "schedule_task",\n')
    replace(package / "claude_parity.py", '"background_agent", "github_monitor",\n',
            '"background_agent", "github_monitor", "schedule_task",\n')

    sv = package / "service.py"
    replace(sv, "        fleet.SERVICE = self\n",
            "        fleet.SERVICE = self\n        from . import schedule\n        schedule.SERVICE = self\n")
    replace(sv, "        from . import fleet\n        out = fleet.command(self, s, name, args)\n",
            "        from . import schedule\n        out = schedule.command(self, s, name, args)\n"
            "        if out is not None:\n            return out\n"
            "        from . import fleet\n        out = fleet.command(self, s, name, args)\n")
    replace(sv, '    ("bg", "<task>", "Start a background agent on a task (its own worktree; keeps going while you work)"),\n',
            '    ("bg", "<task>", "Start a background agent on a task (its own worktree; keeps going while you work)"),\n'
            '    ("schedule", "[daily 08:00 | weekly mon,fri 18:00 | every 3h | once tomorrow 15:00 | in 30m] <task>",\n'
            '     "Scheduled tasks: add one, or list them; pause|resume|remove|run <id>"),\n'
            '    ("duet", "[on [08:00] [3h] | off]", "The proactive assistant: a morning brief and a quiet check-in"),\n')

    srv = package / "server.py"
    replace(srv, '            if path == "/api/fleet" or path.startswith("/api/gh/"):\n',
            '            if path == "/api/schedules":\n'
            '                from . import schedule\n'
            '                return self._json(schedule.route(svc, "GET", path, q, None))\n'
            '            if path == "/api/fleet" or path.startswith("/api/gh/"):\n')
    replace(srv, '            if path.startswith(("/api/fleet/", "/api/gh/")):\n',
            '            if path.startswith("/api/schedules/"):\n'
            '                from . import schedule\n'
            '                return self._json(schedule.route(svc, "POST", path, None, b))\n'
            '            if path.startswith(("/api/fleet/", "/api/gh/")):\n')
    replace(srv, "    httpd.automatic_stop = auto_update.start(Handler.service)\n",
            "    httpd.automatic_stop = auto_update.start(Handler.service)\n"
            "    from . import schedule\n"
            "    httpd.schedule_stop = schedule.start(Handler.service)\n")
    replace(srv, "        dependency_stop = getattr(self, \"dependency_stop\", None)\n",
            "        schedule_stop = getattr(self, \"schedule_stop\", None)\n"
            "        if schedule_stop is not None:\n"
            "            schedule_stop.set()\n"
            "        dependency_stop = getattr(self, \"dependency_stop\", None)\n")

    with open(package / "claude_parity_tests.py", "a", encoding="utf-8") as f:
        f.write("\nfrom .ext_schedule_tests import ScheduleTests  # noqa: E402,F401 - run with the parity tests in CI\n")
