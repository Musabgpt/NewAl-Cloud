"""Scheduled tasks and a proactive assistant (Grok's Tasks, Claude Duet).

A task is a request the agent does on its own at its time: once, every day, on some days of the week, or every N
minutes (inside some hours of the day, when given). Each task has one thread of its own (listed with the background
agents, with the model and permission mode of the thread it was made in): every run continues it, so a run sees what
the earlier runs did, and a journal of what each run did (its last answer) comes with every run, with the rule to
never do again what is done (the same post twice). The user changes the task from that thread too ("make it 9pm"):
schedule_task edits the thread's own task. Android says how a run went. A quiet task (the check-in) speaks only when
something needs the user: its answer NOTHING_NEW posts nothing.

/duet on adds two such tasks: the morning brief (every day at 08:00) and the check-in (every 3 hours, 08:00-22:00,
quiet). What the thread's permission mode asks approval for still asks: the notification has Allow and Deny.

On the phone, Android wakes the engine at the next task's time (an alarm the app sets and keeps across reboots), so a
task runs with the screen off. A task that works the phone's screen (phone) runs one at a time and the app turns the
screen on first. With a PIN, pattern or fingerprint lock Android lets no app unlock the phone: the task waits, a
notification asks to unlock, and it starts within half a minute of the unlock. A time missed while the phone was off
runs once when the engine is back, not once per missed time.
"""
import datetime
import json
import os
import re
import threading
import time

NAMES = ["schedule_task"]
SERVICE = None                       # the app's Service, set when it starts
TICK = 30                            # seconds between looks at the clock
MAX_TASKS = 50
MAX_RUNNING = 4                      # runs at the same time (only one of them on the phone's screen)
MIN_EVERY = 15                       # minutes: the shortest repeat
QUIET = "NOTHING_NEW"
KINDS = ("once", "daily", "weekly", "every")
DAYS = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6,
        "الاثنين": 0, "الإثنين": 0, "اثنين": 0, "الثلاثاء": 1, "ثلاثاء": 1, "الأربعاء": 2, "الاربعاء": 2,
        "اربعاء": 2, "الخميس": 3, "خميس": 3, "الجمعة": 4, "جمعة": 4, "السبت": 5, "سبت": 5, "الأحد": 6,
        "الاحد": 6, "احد": 6}
DAY_LABELS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
TODAY = ("today", "اليوم")
TOMORROW = ("tomorrow", "بكرا", "بكره", "بكرة", "غدا", "غداً")
# a task that does something in an app (opens it, sends, taps) works the phone's screen: it runs alone, with the
# screen on. Reading the notifications needs no screen.
PHONE_WORDS = ("on the phone", "open the app", "tap ", "على الجوال", "بالجوال", "على الموبايل", "افتح تطبيق",
               "افتح التطبيق", "اضغط")
APP_VERBS = ("open", "send", "tap", "play", "post", "reply", "call", "افتح", "فتح", "ابعت", "ارسل", "أرسل", "رد ",
             "شغل", "شغّل", "اتصل", "انشر")

RUN = ("⏰ Scheduled task %(id)s «%(name)s» (%(when)s): run %(n)d, %(now)s.\n\nThe task: %(prompt)s\n\n%(journal)s"
       "(This thread is this task's own: every run continues it. Nobody is watching it now. Before acting, read what the "
       "earlier runs did (this thread above, and the list): never do again what is already done - never post the same "
       "text or picture twice, never send the same message twice, never repeat the same work; make this run's work "
       "new, following on from the last one. If the task cannot be done without repeating, say so and do nothing. Do "
       "the whole task without asking questions; when something is unclear make the reasonable choice and say which. "
       "What your permission mode asks approval for is sent to the user's phone: if it is denied, do not try another "
       "way, say so. Never send a message, pay, delete or publish anything the task did not ask for. End with what you "
       "did exactly (e.g. the text you posted): the next runs read it, and your last answer becomes a phone "
       "notification, the result first, short. The user may write in this thread to change the task (its time, "
       "its instructions): schedule_task action=edit changes this thread's task.%(quiet)s)")
JOURNAL = 12                         # the earlier runs listed with each run (all of them stay in the thread)
QUIET_BRIEF = (" Speak only when something needs the user's attention now. If nothing does, answer exactly "
               + QUIET + " and nothing else.")

MORNING = ("Morning brief. Look at what came in since yesterday: the phone's notifications (phone "
           "action=notifications_read, when it is on), GitHub (the project's Actions runs and pull requests) and the "
           "connected services you have tools for. Write a short brief: the most important items first, one line "
           "each, and what needs a reply or an action today. Skip a source you cannot reach in a few words. Write in "
           "the language of the user's messages (Arabic when unsure).")
CHECKIN = ("Check-in. Look at what came in since the previous run: the phone's notifications (phone "
           "action=notifications_read, when it is on), GitHub Actions runs and pull requests, and the connected "
           "services you have tools for. Only something that needs the user now counts: a direct message waiting for "
           "a reply, a failed build, a deadline today, a security alert. Write it in one to three lines, in the "
           "language of the user's messages (Arabic when unsure).")

_LOCK = threading.RLock()
_runs = {}                           # session id -> task id: the runs going now
_armed = [0]                         # the alarm time the app was last given (0: none)


class ScheduleError(ValueError):
    pass


def _path():
    from . import settings
    return os.path.join(settings.HOME, "schedules.json")


def load():
    try:
        with open(_path(), encoding="utf-8") as f:
            d = json.load(f)
        return [t for t in d.get("tasks") or [] if isinstance(t, dict) and t.get("id")]
    except (OSError, ValueError, AttributeError):
        return []


def save(tasks):
    path = _path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"tasks": tasks}, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def is_run(sid):
    """A scheduled run is going in this thread (it reports through the scheduler, not the end-of-turn notification)."""
    return bool(sid) and sid in _runs


def task_of(sid):
    """The task whose own thread this is, or None."""
    if not sid:
        return None
    with _LOCK:
        return next((t for t in load() if t.get("session") == sid), None)


# ------------------------------------------------------------------ when

def _digits(s):
    return str(s or "").strip().translate(str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789"))


def _hm(at):
    m = re.fullmatch(r"(\d{1,2})(?::(\d{2}))?", _digits(at))
    if not m or int(m.group(1)) > 23 or int(m.group(2) or 0) > 59:
        raise ScheduleError("time: HH:MM, e.g. 08:00 or 18:30 (24 hours, the phone's time)")
    return "%02d:%02d" % (int(m.group(1)), int(m.group(2) or 0))


def _days(days):
    if isinstance(days, str):
        days = re.split(r"[\s,،]+", days.strip())
    out = set()
    for d in days or []:
        d = _digits(d).lower()
        if d.isdigit() and int(d) < 7:
            out.add(int(d))
        elif d[:3] in DAYS:
            out.add(DAYS[d[:3]])
        elif d in DAYS:
            out.add(DAYS[d])
        elif d:
            raise ScheduleError("unknown day %r: mon, tue, wed, thu, fri, sat, sun" % d)
    if not out:
        raise ScheduleError("weekly needs days, e.g. mon,thu")
    return sorted(out)


def _minutes(every):
    """3h, 90m, 1d, 45 (minutes) -> minutes."""
    m = re.fullmatch(r"(\d+(?:\.\d+)?)\s*(m|min|minutes?|h|hours?|d|days?)?", _digits(every).lower())
    if not m:
        raise ScheduleError("every: minutes or hours, e.g. 30m, 3h, 1d")
    unit = (m.group(2) or "m")[0]
    n = int(round(float(m.group(1)) * {"m": 1, "h": 60, "d": 1440}[unit]))
    if n < MIN_EVERY:
        raise ScheduleError("the shortest repeat is every %d minutes" % MIN_EVERY)
    return n


def _window(window):
    if not window:
        return None
    if isinstance(window, (list, tuple)) and len(window) == 2:
        a, b = window
    else:
        m = re.fullmatch(r"(\d{1,2})(?::00)?\s*[-–]\s*(\d{1,2})(?::00)?", _digits(window))
        if not m:
            raise ScheduleError("hours: from-to in whole hours, e.g. 08-22")
        a, b = m.groups()
    a, b = int(a), int(b)
    if not (0 <= a < b <= 24):
        raise ScheduleError("hours: from-to in whole hours, e.g. 08-22")
    return [a, b]


def when_of(kind, at="", date="", days=None, every=None, in_minutes=None, window=None, now=None):
    """The checked `when` of a task, from the tool's (or the command's) fields."""
    kind = str(kind or "").strip().lower()
    now = time.time() if now is None else now
    if in_minutes not in (None, "") and kind in ("", "once"):
        return {"kind": "once", "ts": round(now + max(1, int(float(_digits(in_minutes)))) * 60)}
    if kind not in KINDS:
        raise ScheduleError("kind: once, daily, weekly or every")
    if kind == "every":
        return {"kind": "every", "minutes": _minutes(every), "window": _window(window)}
    hm = _hm(at)
    if kind == "daily":
        return {"kind": "daily", "at": hm}
    if kind == "weekly":
        return {"kind": "weekly", "at": hm, "days": _days(days)}
    h, m = map(int, hm.split(":"))
    today = datetime.datetime.fromtimestamp(now).date()
    d = str(date or "").strip().lower()
    if not d:
        day = today if datetime.datetime.combine(today, datetime.time(h, m)).timestamp() > now else \
            today + datetime.timedelta(days=1)
    elif d in TODAY:
        day = today
    elif d in TOMORROW:
        day = today + datetime.timedelta(days=1)
    else:
        try:
            day = datetime.date.fromisoformat(_digits(d))
        except ValueError:
            raise ScheduleError("date: YYYY-MM-DD, today or tomorrow")
    ts = datetime.datetime.combine(day, datetime.time(h, m)).timestamp()
    if ts <= now:
        raise ScheduleError("%s is already past" % _fmt(ts))
    return {"kind": "once", "ts": round(ts)}


def next_run(when, after):
    """The first time after `after` (seconds) the task runs, in the phone's local time; None: never again."""
    kind = when.get("kind")
    if kind == "once":
        return when["ts"] if when["ts"] > after else None
    if kind == "every":
        nxt = after + when["minutes"] * 60
        win = when.get("window")
        if win:
            dt = datetime.datetime.fromtimestamp(nxt)
            if dt.hour < win[0]:
                nxt = datetime.datetime.combine(dt.date(), datetime.time(win[0])).timestamp()
            elif dt.hour >= win[1]:
                nxt = datetime.datetime.combine(dt.date() + datetime.timedelta(days=1),
                                                datetime.time(win[0])).timestamp()
        return round(nxt)
    h, m = map(int, when["at"].split(":"))
    day = datetime.datetime.fromtimestamp(after).date()
    for i in range(8):
        d = day + datetime.timedelta(days=i)
        ts = datetime.datetime.combine(d, datetime.time(h, m)).timestamp()
        if ts > after and (kind == "daily" or d.weekday() in when.get("days", ())):
            return round(ts)
    return None


def _following(t, now):
    """The next time after the one that is due now: times missed while the phone was off are skipped."""
    nxt = next_run(t["when"], t.get("next") or now)
    if nxt is not None and nxt <= now:
        nxt = next_run(t["when"], now)
    return nxt


def _fmt(ts):
    return datetime.datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M (%a)") if ts else "-"


def describe(when):
    kind = when.get("kind")
    if kind == "once":
        return "once, " + _fmt(when["ts"])
    if kind == "daily":
        return "every day at " + when["at"]
    if kind == "weekly":
        return "%s at %s" % (", ".join(DAY_LABELS[d] for d in when["days"]), when["at"])
    n = when["minutes"]
    text = "every %s" % ("%dh" % (n // 60) if n % 60 == 0 else "%dm" % n)
    if when.get("window"):
        text += " (%02d:00-%02d:00)" % tuple(when["window"])
    return text


# ------------------------------------------------------------------ the tasks

def _guess_phone(prompt):
    text = " " + str(prompt or "").lower() + " "
    try:
        from . import phone_fast
        if any(name in text for name in phone_fast.APP_NAMES) and any(v in text for v in APP_VERBS):
            return True
    except Exception:  # noqa: BLE001 - without the phone layer no task is a phone task
        pass
    return any(w in text for w in PHONE_WORDS)


def _public(t):
    out = {k: t.get(k) for k in ("id", "name", "prompt", "enabled", "next", "quiet", "phone", "preset", "pending",
                                  "waiting_unlock", "created", "root")}
    out["when"] = t["when"]
    out["schedule"] = describe(t["when"])
    out["last"] = dict(t.get("last") or {})
    out["session"] = t.get("session") or ""
    out["runs"] = t.get("runs") or 0
    out["history"] = list(t.get("history") or [])[-5:]
    out["running"] = bool(t.get("session")) and t.get("session") in _runs
    return out


def listing():
    with _LOCK:
        return [_public(t) for t in load()]


def _find(tasks, tid):
    tid = str(tid or "").strip()
    for t in tasks:
        if t["id"] == tid:
            return t
    raise ScheduleError("no task %s (schedule_task action=list shows them)" % (tid or "(no id)"))


def add(session, prompt, when, name="", quiet=False, phone=None, preset=None, now=None):
    prompt = str(prompt or "").strip()
    if not prompt:
        raise ScheduleError("a task needs what to do (prompt)")
    now = time.time() if now is None else now
    with _LOCK:
        tasks = load()
        if len(tasks) >= MAX_TASKS:
            raise ScheduleError("%d tasks already (the most): remove one first" % len(tasks))
        num = max([int(t["id"][1:]) for t in tasks if re.fullmatch(r"t\d+", t["id"])] + [0]) + 1
        words = re.sub(r"\s+", " ", prompt)
        t = {"id": "t%d" % num, "name": (str(name or "").strip() or (words[:40] + ("…" if len(words) > 40 else "")))[:60],
             "prompt": prompt[:4000], "when": when, "enabled": True, "quiet": bool(quiet),
             "phone": _guess_phone(prompt) if phone is None else bool(phone), "preset": preset, "created": round(now),
             "root": getattr(session, "origin", "") or getattr(session, "root", ""),
             "model": getattr(session, "model", None), "mode": getattr(session, "mode", None),
             "parent": getattr(session, "id", ""), "last": {}, "pending": False}
        t["next"] = next_run(when, now)
        if t["next"] is None:
            raise ScheduleError("that time is already past")
        if SERVICE is not None:
            try:
                t["session"] = _thread(SERVICE, t).id   # its own thread now: the user can open it and change it
            except Exception:  # noqa: BLE001 - the first run makes it then
                pass
        tasks.append(t)
        save(tasks)
    _arm()
    return t


def _thread(service, t):
    """The task's own thread: made once (again only when it was deleted), and every run continues it."""
    from . import fleet
    sid = t.get("session")
    if sid:
        try:
            return service.get(sid)
        except Exception:  # noqa: BLE001 - deleted: a new one
            pass
    root = t.get("root") or ""
    if not os.path.isdir(root):
        root = (service.projects() or [os.path.expanduser("~")])[0]
    s = service.create(root, model=t.get("model") or None, mode=t.get("mode") or None)
    s.title = "⏰ " + t["name"]
    s.save_meta()
    with fleet._LOCK:
        reg = fleet._load()
        reg[s.id] = {"parent": t.get("parent") or "", "name": "⏰ " + t["name"], "prompt": t["prompt"],
                     "started": time.time(), "worktree": False, "root": root, "task": t["id"]}
        fleet._save(reg)
    t["session"] = s.id
    return s


def change(tid, **fields):
    """pause (enabled=False), resume (enabled=True), or new fields (name, prompt, when, quiet, phone)."""
    with _LOCK:
        tasks = load()
        t = _find(tasks, tid)
        for k in ("name", "prompt", "quiet", "phone"):
            if fields.get(k) is not None:
                t[k] = fields[k] if k in ("quiet", "phone") else str(fields[k]).strip()[:4000 if k == "prompt" else 60]
        if fields.get("when"):
            t["when"] = fields["when"]
            t["next"] = next_run(t["when"], time.time())
            t["enabled"] = t["next"] is not None     # a done one-time task with a new time runs again
        if fields.get("enabled") is not None:
            t["enabled"] = bool(fields["enabled"])
            if t["enabled"] and (not t.get("next") or t["next"] <= time.time()):
                t["next"] = next_run(t["when"], time.time())
                if t["next"] is None:
                    raise ScheduleError("its time is past: give it a new time")
            if not t["enabled"]:
                t["pending"] = t["waiting_unlock"] = False
        save(tasks)
    _arm()
    return t


def remove(tid):
    with _LOCK:
        tasks = load()
        t = _find(tasks, tid)
        save([x for x in tasks if x is not t])
    _arm()
    return t


def run_now(service, tid):
    with _LOCK:
        tasks = load()
        t = _find(tasks, tid)
        t["pending"] = True
        save(tasks)
    tick(service)
    return t


def duet(session, on=True, at="08:00", every="3h", window="08-22"):
    """The proactive assistant: the morning brief and the quiet check-in, as two tasks (or neither)."""
    with _LOCK:
        save([t for t in load() if t.get("preset") not in ("brief", "checkin")])
        if not on:
            _arm()
            return []
        brief = add(session, MORNING, when_of("daily", at=at), name="☀ Morning brief", preset="brief", phone=False)
        check = add(session, CHECKIN, when_of("every", every=every, window=window), name="🔔 Check-in", quiet=True,
                    preset="checkin", phone=False)
        return [brief, check]


# ------------------------------------------------------------------ the clock

def _phone():
    from . import phone
    return phone


def _phone_call(action, **args):
    try:
        if not _phone().available():
            return None
        return _phone().call(action, timeout=20, **args)
    except Exception:  # noqa: BLE001 - the phone's help is a courtesy: the clock goes on without it
        return None


def _arm():
    """Tells Android when to wake the engine next (the earliest task), when that changed."""
    with _LOCK:
        times = [t["next"] for t in load() if t.get("enabled") and t.get("next")]
    at = int(min(times) * 1000) if times else 0
    if at != _armed[0] and _phone_call("schedule_alarm", at=at) is not None:
        _armed[0] = at


def _wake():
    """Before a run on the screen: "on" (the screen is on and unlocked, or the app turned it on), "woke" (the app
    turned it on for this run) or "locked" (a secure lock only the user opens)."""
    r = _phone_call("wake")
    if not r:
        return "on"
    if r.get("locked"):
        return "locked"
    return "woke" if r.get("woke") else "on"


def tick(service, now=None):
    """Due tasks become pending; pending tasks start while there is room (and the screen, for a phone task)."""
    if service is None:
        return
    now = time.time() if now is None else now
    with _LOCK:
        tasks = load()
        changed = False
        for t in tasks:
            last = t.get("last") or {}
            if last.get("state") == "running" and last.get("session") not in _runs:
                last["state"] = "stopped"                   # the engine stopped during that run
                changed = True
            if t.get("enabled") and t.get("next") and t["next"] <= now:
                t["pending"] = True
                t["next"] = _following(t, now)
                if t["next"] is None:
                    t["enabled"] = False                    # a one-time task, done
                changed = True
        running = [sid for sid in _runs if service.busy(sid)]
        screen = any(_runs[sid] == t["id"] and t.get("phone") for sid in running for t in tasks)
        for t in sorted((t for t in tasks if t.get("pending")), key=lambda t: t.get("created", 0)):
            if len(running) >= MAX_RUNNING:
                break
            if t.get("session") and service.busy(t["session"]):
                continue                    # its thread is working (its previous time, or the user writing in it)
            woke = False
            if t.get("phone"):
                if screen:
                    continue
                state = _wake()
                if state == "locked":
                    if not t.get("waiting_unlock"):
                        t["waiting_unlock"] = True
                        changed = True
                        _phone_call("notify", title="⏰ " + t["name"],
                                    text="مهمة مجدولة تنتظر: افتح قفل الجوال لتبدأ\n"
                                         "A scheduled task is waiting: unlock the phone to start it")
                    continue
                woke, screen = state == "woke", True
            try:
                sid = _start(service, t, woke)
            except Exception as e:  # noqa: BLE001 - one task's failure never stops the others
                t["last"] = {"time": round(now), "state": "error", "answer": str(e)[:300]}
                t["pending"] = False
                changed = True
                continue
            running.append(sid)
            t["pending"] = t["waiting_unlock"] = False
            changed = True
        if changed:
            save(tasks)
    _arm()


def _journal(t):
    done = [h for h in t.get("history") or [] if h.get("state") in ("done", "quiet")][-JOURNAL:]
    if not done:
        return "This is its first run.\n\n"
    lines = ["- %s: %s" % (_fmt(h.get("time")), "nothing new" if h.get("state") == "quiet" else
                           re.sub(r"\s+", " ", h.get("answer") or "")[:400]) for h in done]
    return "What the earlier runs did (oldest first):\n" + "\n".join(lines) + "\n\n"


def message(t, now=None):
    """What a run sends to the task's thread: the task, the journal of the earlier runs, and the rules."""
    prev = (t.get("last") or {}).get("time")
    quiet = QUIET_BRIEF + (" The previous run was at %s." % _fmt(prev) if prev else "") if t.get("quiet") else ""
    return RUN % {"id": t["id"], "name": t["name"], "when": describe(t["when"]), "n": (t.get("runs") or 0) + 1,
                  "now": _fmt(time.time() if now is None else now), "prompt": t["prompt"], "journal": _journal(t),
                  "quiet": " " + quiet.strip() if quiet else ""}


def _start(service, t, woke):
    s = _thread(service, t)
    _runs[s.id] = t["id"]
    out = service.send(s.id, message(t))
    if not out.get("started"):
        _runs.pop(s.id, None)
        raise ScheduleError(out.get("reply") or "the task did not start")
    t["runs"] = (t.get("runs") or 0) + 1
    t["last"] = {"time": round(time.time()), "session": s.id, "state": "running"}
    _phone_call("keep_awake", seconds=600)
    service.broadcast({"type": "fleet", "state": "start", "session": t.get("parent") or "", "agent": s.id,
                       "name": "⏰ " + t["name"]})
    service.broadcast({"type": "schedule", "state": "start", "task": t["id"], "agent": s.id})
    threading.Thread(target=_watch, args=(service, t["id"], s.id, woke), name="musab-schedule-run",
                     daemon=True).start()
    return s.id


def _watch(service, tid, sid, woke, poll=3):
    """Until the run ends; then its result: a notification (none for a quiet task with nothing to say)."""
    from . import fleet
    beat = time.time()
    while service.busy(sid):
        if time.time() - beat > 300:
            _phone_call("keep_awake", seconds=600)          # the CPU stays awake while the run works
            beat = time.time()
        time.sleep(poll)
    try:
        answer = fleet._answer(service.get(sid))
    except Exception:  # noqa: BLE001
        answer = ""
    quiet = answer.strip().startswith(QUIET)
    state = "quiet" if quiet else ("done" if answer else "stopped")
    name = tid
    with _LOCK:
        _runs.pop(sid, None)
        tasks = load()
        for t in tasks:
            if t["id"] == tid:
                name = t["name"]
                t["last"] = dict(t.get("last") or {}, session=sid, state=state, answer=answer[:600],
                                 ended=round(time.time()))
                # the journal the next runs read: what each run did, so none does it again
                t["history"] = (list(t.get("history") or []) + [{k: t["last"].get(k) for k in
                                                                 ("time", "state", "answer")}])[-30:]
        save(tasks)
    if not quiet:
        _phone_call("notify", title="⏰ " + name, text=answer[:600] or "انتهت المهمة بدون نتيجة / ended without an "
                                                                      "answer", only_background=True)
    if woke:
        _phone_call("sleep_screen")
    if not _runs:
        _phone_call("keep_awake", seconds=0)
    service.broadcast({"type": "schedule", "state": "end", "task": tid, "agent": sid, "result": state})
    tick(service)


def start(service):
    """The clock: a look every half minute (Android's alarm wakes the engine for the next task). Returns its stop."""
    if os.environ.get("NEWAL_DISABLE_AUTOMATION") == "1" or os.environ.get("NEWAL_DISABLE_SCHEDULE") == "1":
        return None
    stop = threading.Event()

    def work():
        while not stop.is_set():
            try:
                tick(service)
            except Exception:  # noqa: BLE001 - the clock never dies of one bad look
                pass
            stop.wait(TICK)
    threading.Thread(target=work, name="musab-schedule", daemon=True).start()
    return stop


# ------------------------------------------------------------------ the tool

def _line(t):
    p = _public(t) if "schedule" not in t else t
    state = "⏸ paused" if not p["enabled"] else ("⏳ running" if p["running"] else (
        "🔒 waiting for unlock" if p.get("waiting_unlock") else ("… due" if p.get("pending") else "next " + _fmt(p["next"]))))
    flags = "".join([" quiet" if p.get("quiet") else "", " phone-screen" if p.get("phone") else ""])
    out = "%s  %s  [%s · %s%s]" % (p["id"], p["name"], p["schedule"], state, flags)
    last = p.get("last") or {}
    if last.get("state") and last.get("state") != "running":
        out += "\n  last: %s %s%s" % (_fmt(last.get("time")), last["state"],
                                      (": " + last["answer"][:160].replace("\n", " ")) if last.get("answer") else "")
    return out


def _report(tasks):
    head = "Now: %s (the phone's time)." % _fmt(time.time())
    if not tasks:
        return head + "\nNo scheduled tasks yet."
    return head + "\n" + "\n".join(_line(t) for t in tasks)


def _when_from(kind, at, date, days, every, in_minutes, window):
    if not kind and in_minutes in (None, ""):
        return None
    return when_of(kind, at=at, date=date, days=days, every=every, in_minutes=in_minutes, window=window)


def install():
    from . import tools

    @tools.tool("schedule_task",
                "Scheduled tasks: work done on its own at a time - once, every day, some days of the week, or every N "
                "minutes - in the task's own thread of this project (every run continues it and sees what the earlier "
                "runs did); the user's phone shows the result. In a task's own thread, edit/pause/resume/remove/run "
                "without id act on that task: when the user asks there to change it, edit it. Times are "
                "the phone's local time (action=list shows the time now). action=add: prompt (the whole task, as an "
                "instruction to yourself at that time), name, kind (once: at + date YYYY-MM-DD/today/tomorrow, or "
                "in_minutes; daily: at HH:MM; weekly: at + days 'mon,thu'; every: every '3h'/'30m', hours '08-22'), "
                "quiet (only notify when something needs the user), phone (it works the phone's screen: guessed when "
                "left out). Several tasks in one request: add each; if any time or task is unclear, list them back "
                "and ask first. action=list; edit (id + fields); pause, resume, remove, run (id: now); duet "
                "(on: true/false, at, every, hours): the morning brief and the quiet check-in.",
                {"action": tools._s("add, list, edit, pause, resume, remove, run or duet"),
                 "prompt": tools._s("add/edit: what to do at that time, complete"),
                 "name": tools._s("add/edit: a short name"),
                 "kind": tools._s("add/edit: once, daily, weekly or every"),
                 "at": tools._s("once/daily/weekly; duet: the brief's time, HH:MM (24 h)"),
                 "date": tools._s("once: YYYY-MM-DD, today or tomorrow (default: the next such time)"),
                 "in_minutes": {"type": "integer", "description": "once: this many minutes from now"},
                 "days": tools._s("weekly: days, e.g. mon,thu"),
                 "every": tools._s("every; duet: the check-in's repeat, e.g. 3h or 30m (at least 15m)"),
                 "hours": tools._s("every; duet: only between these hours, e.g. 08-22"),
                 "quiet": {"type": "boolean", "description": "notify only when something needs the user"},
                 "phone": {"type": "boolean", "description": "the task works the phone's screen"},
                 "on": {"type": "boolean", "description": "duet: turn the brief and check-in on (default) or off"},
                 "id": tools._s("edit, pause, resume, remove, run: the task's id, e.g. t3 (in a task's own thread: "
                                "that task by default)")},
                ["action"], "meta")
    def t_schedule_task(ctx, action, prompt="", name="", kind="", at="", date="", in_minutes=None, days="",
                        every="", hours="", quiet=None, phone=None, on=True, id=""):  # noqa: A002 - the param's name
        action = str(action or "").strip().lower()
        if not str(id or "").strip() and action in ("edit", "pause", "resume", "remove", "run"):
            own = task_of(getattr(ctx.session, "id", ""))
            id = own["id"] if own else id  # noqa: A001
        try:
            if action == "add":
                if getattr(ctx.agent, "depth", 0):
                    raise ScheduleError("a sub-agent cannot schedule tasks")
                when = _when_from(kind, at, date, days, every, in_minutes, hours)
                if when is None:
                    raise ScheduleError("kind: once, daily, weekly or every (or in_minutes)")
                t = add(ctx.session, prompt, when, name=name, quiet=bool(quiet), phone=phone)
                return ("Scheduled %s «%s»: %s; next run %s. It has its own thread: every run continues it, and the "
                        "user can change the task there.%s" % (
                    t["id"], t["name"], describe(t["when"]), _fmt(t["next"]),
                    " It works the phone's screen: it runs alone, with the screen turned on (a locked phone asks "
                    "the user to unlock)." if t["phone"] else "")), {"task": t["id"], "next": t["next"]}
            if action == "list":
                items = listing()
                return _report(items), {"tasks": len(items)}
            if action in ("pause", "resume"):
                t = change(id, enabled=action == "resume")
                return "%s %s." % (t["id"], "paused" if action == "pause" else "resumed: next " + _fmt(t["next"])), \
                    {"task": t["id"]}
            if action == "edit":
                t = change(id, name=name or None, prompt=prompt or None, quiet=quiet, phone=phone,
                           when=_when_from(kind, at, date, days, every, in_minutes, hours))
                return "Changed: " + _line(t), {"task": t["id"]}
            if action == "remove":
                t = remove(id)
                return "Removed %s «%s»." % (t["id"], t["name"]), {"task": t["id"]}
            if action == "run":
                if SERVICE is None:
                    raise ScheduleError("tasks run in the MusabAI app (its engine runs them)")
                t = run_now(SERVICE, id)
                return "%s «%s» starts now (in its own thread)." % (t["id"], t["name"]), {"task": t["id"]}
            if action == "duet":
                made = duet(ctx.session, on is not False, at=at or "08:00", every=every or "3h",
                            window=hours or "08-22")
                if not made:
                    return "The morning brief and the check-in are off.", {"tasks": 0}
                return "On:\n" + "\n".join(_line(t) for t in made), {"tasks": len(made)}
        except ScheduleError as e:
            raise tools.ToolError(str(e))
        raise tools.ToolError("action: add, list, edit, pause, resume, remove, run or duet")


# ------------------------------------------------------------------ slash commands and the app's routes

COMMANDS = [
    ("schedule", "[daily 08:00 | weekly mon,fri 18:00 | every 3h | once tomorrow 15:00 | in 30m] <task>",
     "Scheduled tasks: add one, or list them; pause|resume|remove|run <id>"),
    ("duet", "[on [08:00] [3h] | off]", "The proactive assistant: a morning brief and a quiet check-in"),
]


def parse(args, now=None):
    """'/schedule' text -> (when, task); None when it is not in the short form (the model reads it instead)."""
    words = str(args or "").split()
    if len(words) < 2:
        return None
    head = words[0].lower()
    if head == "daily" and len(words) >= 3:
        return when_of("daily", at=words[1], now=now), " ".join(words[2:])
    if head == "weekly" and len(words) >= 4:
        return when_of("weekly", days=words[1], at=words[2], now=now), " ".join(words[3:])
    if head == "every" and len(words) >= 3:
        rest = words[2:]
        window = None
        if re.fullmatch(r"\d{1,2}-\d{1,2}", _digits(rest[0])) and len(rest) >= 2:
            window, rest = rest[0], rest[1:]
        return when_of("every", every=words[1], window=window, now=now), " ".join(rest)
    if head == "in" and len(words) >= 3:
        return when_of("once", in_minutes=_minutes_or_plain(words[1]), now=now), " ".join(words[2:])
    if head == "once" and len(words) >= 3:
        if re.fullmatch(r"\d{1,2}(:\d{2})?", _digits(words[1])):
            return when_of("once", at=words[1], now=now), " ".join(words[2:])
        if len(words) >= 4:
            return when_of("once", date=words[1], at=words[2], now=now), " ".join(words[3:])
    return None


def _minutes_or_plain(v):
    m = re.fullmatch(r"(\d+(?:\.\d+)?)\s*(m|min|h|d)?", _digits(v).lower())
    if not m:
        raise ScheduleError("in: minutes or hours, e.g. 30m or 2h")
    return int(round(float(m.group(1)) * {"m": 1, "h": 60, "d": 1440}[(m.group(2) or "m")[0]]))


def command(service, s, name, args):
    try:
        if name == "schedule":
            words = args.split()
            if not words:
                return {"reply": "⏰ " + _report(listing())}
            if words[0].lower() in ("pause", "resume", "remove", "delete", "run") and len(words) == 2:
                act, tid = words[0].lower(), words[1]
                if act in ("remove", "delete"):
                    t = remove(tid)
                    return {"reply": "⏰ Removed %s «%s»." % (t["id"], t["name"])}
                if act == "run":
                    t = run_now(service, tid)
                    return {"reply": "⏰ %s «%s» starts now." % (t["id"], t["name"])}
                t = change(tid, enabled=act == "resume")
                return {"reply": "⏰ " + _line(t)}
            short = parse(args)
            if short is None:
                # natural words ("كل يوم الساعة 8 لخصلي الأخبار"): the model reads them and calls schedule_task
                return {"prompt": "Schedule this with the schedule_task tool (several tasks: add each): " + args}
            when, task = short
            t = add(s, task, when)
            return {"reply": "⏰ Scheduled %s «%s»: %s; next run %s." % (t["id"], t["name"], describe(t["when"]),
                                                                       _fmt(t["next"]))}
        if name == "duet":
            words = args.lower().split()
            if words and words[0] == "off":
                duet(s, False)
                return {"reply": "⏰ The morning brief and the check-in are off."}
            at = next((w for w in words if ":" in w), "08:00")
            every = next((w for w in words if w[-1:] in ("h", "m") and ":" not in w), "3h")
            made = duet(s, True, at=at, every=every)
            return {"reply": "⏰ On:\n" + "\n".join(_line(t) for t in made)}
    except ScheduleError as e:
        return {"reply": "⏰ " + str(e)}
    return None


def route(service, method, path, q=None, b=None):
    """The app's /api/schedules routes: a JSON-able answer."""
    q, b = q or {}, b or {}
    try:
        if path == "/api/schedules" and method == "GET":
            return {"tasks": listing(), "now": time.time()}
        if method != "POST":
            return {"error": "not found"}
        act = path.rsplit("/", 1)[-1]
        if act == "add":
            when = _when_from(b.get("kind"), b.get("at"), b.get("date"), b.get("days"), b.get("every"),
                              b.get("in_minutes"), b.get("hours"))
            if when is None:
                raise ScheduleError("kind: once, daily, weekly or every")
            t = add(service.get(str(b.get("session") or "")), b.get("prompt"), when, name=b.get("name") or "",
                    quiet=bool(b.get("quiet")), phone=b.get("phone"))
            return {"ok": True, "task": _public(t)}
        if act == "edit":
            when = _when_from(b.get("kind"), b.get("at"), b.get("date"), b.get("days"), b.get("every"),
                              b.get("in_minutes"), b.get("hours"))
            return {"ok": True, "task": _public(change(b.get("id"), name=b.get("name") or None,
                                                       prompt=b.get("prompt") or None, quiet=b.get("quiet"),
                                                       phone=b.get("phone"), when=when))}
        if act in ("pause", "resume"):
            return {"ok": True, "task": _public(change(b.get("id"), enabled=act == "resume"))}
        if act == "remove":
            return {"ok": True, "task": _public(remove(b.get("id")))}
        if act == "run":
            return {"ok": True, "task": _public(run_now(service, b.get("id")))}
        if act == "duet":
            made = duet(service.get(str(b.get("session") or "")), bool(b.get("on", True)), at=b.get("at") or "08:00",
                        every=b.get("every") or "3h", window=b.get("hours") or "08-22")
            return {"ok": True, "tasks": [_public(t) for t in made]}
    except (ValueError, OSError, KeyError) as e:
        return {"error": str(e)}
    return {"error": "not found"}
