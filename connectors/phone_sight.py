"""The phone by sight, and several steps in one call (two ideas from Google's Artemis).

screen_tap: some screens give the accessibility service nothing to read (games, Flutter and Compose canvases,
pictures, icons without labels), so the screen tool cannot number them. screen_tap finds the target the way a person
does: a vision model looks at a screenshot and points at it, then looks again at a magnified crop around that point
(Artemis's zoom) for the exact spot, and the phone taps there. action=find only says where it is.

phone_steps: a model round trip costs seconds, and controls that fade (a video's play bar, a toast's Undo, a menu that
closes) are gone by the next one. phone_steps runs several phone actions back to back in one call (tap, type, swipe,
key, open_app, wait), each checked. It stops at the first that fails, with the screen as it is then, and returns the
screen at the end. The steps join the turn's phone log, so a task done well this way is learned as a routine too.
"""
import json
import re

from . import tools

NAMES = ["screen_tap", "phone_steps"]
MAX_STEPS = 12
STEP_ACTIONS = ("tap", "type", "swipe", "scroll", "key", "open_app", "open_url", "wait")
ZOOM = 0.4                           # the side of the magnified crop, as a part of the screen's width
WHOLE = "a screenshot of a phone's screen"
PART = "a magnified part of a phone's screenshot"
POINT = ("This is %s. Find this on it: %s\n\nAnswer with JSON only. If it is there: {\"found\": true, \"x\": X, "
         "\"y\": Y}, the centre of that element, X from the image's left edge and Y from its top edge, each on a "
         "0-1000 scale of the image's width and height. If it is not there: {\"found\": false, \"why\": \"what is "
         "there instead, in a few words\"}.")


def parse(text):
    """((x, y) on the 0-1000 scale, "") or (None, why)."""
    m = re.search(r"\{.*\}", text or "", re.S)
    try:
        d = json.loads(m.group(0)) if m else {}
    except ValueError:
        d = {}
    if not isinstance(d, dict):
        d = {}
    if d.get("found") is True:
        try:
            x, y = float(d["x"]), float(d["y"])
        except (KeyError, TypeError, ValueError):
            return None, "the vision model gave no usable point"
        if 0 <= x <= 1000 and 0 <= y <= 1000:
            return (x, y), ""
        return None, "the vision model pointed outside the image"
    return None, str(d.get("why") or text or "not found").strip()[:200]


def point(agent, path, target, what=WHOLE):
    """Where a vision model sees the target on the image: ((x, y) on the 0-1000 scale, "") or (None, why)."""
    from . import phone_ext
    client = getattr(agent, "client", None)
    if client is None or getattr(client, "on_device", False):
        raise tools.ToolError("finding a target by sight needs a vision model, and the model on this phone does not "
                              "see images: add a free Gemini key in Providers, or tap with phone (item or text)")
    msg = [{"role": "user", "content": [{"type": "text", "text": POINT % (what, target)},
                                        {"type": "image_url", "image_url": {"url": phone_ext._encode(path)}}]}]
    comp = client.chat(msg, tools=None, owner=agent.session.id, max_tokens=200, reasoning="off",
                       cancel=getattr(agent, "cancel", None))
    return parse(phone_ext._text(getattr(comp, "content", "") or ""))


def locate(agent, target):
    """((x, y, exact) in screen pixels, "") or (None, why): the whole screen first, then a magnified crop around the
    point the model chose. Without the crop (an older app, or the model misses it there) the first point is used."""
    from . import phone
    shot = phone.call("screenshot", timeout=30)
    full = shot.get("path") or ""
    small = shot.get("preview_path") or full
    width, height = int(shot.get("width") or 0), int(shot.get("height") or 0)
    if not (full and width and height):
        raise tools.ToolError("the phone returned no screenshot")
    first, why = point(agent, small, target, WHOLE)
    if first is None:
        return None, why
    cx, cy = first[0] / 1000 * width, first[1] / 1000 * height
    side = max(1, min(int(width * ZOOM), height))
    left = min(max(0, int(cx - side / 2)), width - side)
    top = min(max(0, int(cy - side / 2)), height - side)
    try:
        crop = phone.call("image_crop", timeout=20, path=full, x=left, y=top, w=side, h=side, max=720)
        fine, _ = point(agent, crop["path"], target, PART)
    except (phone.PhoneError, tools.ToolError, KeyError, OSError, ValueError):
        fine = None
    if fine is None:
        return (round(cx), round(cy), False), ""
    return (round(left + fine[0] / 1000 * side), round(top + fine[1] / 1000 * side), True), ""


def _keep_screen(ctx, screen):
    """The turn's last screen listing (phone_fast), so what follows reads the screen this action left."""
    try:
        from . import phone_fast
        if screen:
            phone_fast._state(ctx)["screen"] = screen
    except Exception:  # noqa: BLE001 - only the listing is missing
        pass


def install():
    @tools.tool("screen_tap",
                "Tap what you see but the screen tool cannot list (a game, a Flutter or Compose canvas, a picture, an "
                "icon without a label): a vision model finds it on a screenshot, looks again at a magnified crop for "
                "the exact spot, and the phone taps there. Describe the target as you would to a person, e.g. 'the "
                "round blue + button at the bottom right'. action=find only says where it is. When the screen tool "
                "lists the target, tap it with phone (item or text): that is faster and exact.",
                {"target": tools._s("what to tap, described: how it looks, its words and where it is on the screen"),
                 "action": tools._s("tap (default) or find")},
                ["target"], "phone")
    def t_screen_tap(ctx, target, action="tap"):
        from . import phone, phone_ext
        if not phone_ext.phone_ready():
            raise tools.ToolError("no phone here: screen_tap needs NewAl Code on Android")
        target = str(target or "").strip()
        action = str(action or "tap").strip().lower()
        if not target:
            raise tools.ToolError("target: what to tap, described")
        if action not in ("tap", "find"):
            raise tools.ToolError("action: tap or find")
        ctx.emit({"type": "status", "text": "Looking for %s…" % target[:80]})
        try:
            found, why = locate(ctx.agent, target)
        except phone.PhoneError as e:
            raise tools.ToolError("no screenshot (%s): screenshots need Android 11 and the phone-control "
                                  "accessibility service" % e)
        if found is None:
            return ("Not found on the screen: %s.\n\nWhat the screen tool reads:\n%s" % (
                why, tools.clip(phone_ext.screen_text(), 4000))), {"found": False}
        x, y, exact = found
        where = "%d,%d%s" % (x, y, "" if exact else " (seen on the whole screen only: less exact)")
        if action == "find":
            return ("%s is at %s, in screen pixels (phone tap with x and y taps it)." % (target, where)), \
                {"found": True, "x": x, "y": y, "exact": exact}
        res = phone.call("tap", x=x, y=y)
        screen = str(res.get("screen") or "") or phone_ext.screen_text()
        _keep_screen(ctx, screen)
        return ("Tapped %s at %s.\n\nScreen now:\n%s" % (target, where, tools.clip(screen, 7000))), \
            {"found": True, "x": x, "y": y, "exact": exact}

    @tools.tool("phone_steps",
                "Several phone actions back to back in one call, with no wait for you between them: for controls "
                "that fade or move (a video's play bar, a toast's Undo, a menu that closes) and for short sequences "
                "you know (open the app, tap the search box, type, press enter). steps: phone actions in order, each "
                "like the phone tool's: {action: tap, item | text | x, y}, {action: type, text}, {action: swipe or "
                "scroll, direction}, {action: key, name}, {action: open_app, name}, {action: open_url, url}, "
                "{action: wait, seconds}. Each is checked; it stops at the first that fails and shows the screen "
                "then. At most %d steps." % MAX_STEPS,
                {"steps": {"type": "array", "items": {"type": "object"}, "description": "the phone actions, in order"}},
                ["steps"], "phone")
    def t_phone_steps(ctx, steps):
        from . import phone, phone_ext, phone_fast
        if not phone_ext.phone_ready():
            raise tools.ToolError("no phone here: phone_steps needs NewAl Code on Android")
        if not isinstance(steps, list) or not steps:
            raise tools.ToolError("steps: a list of phone actions")
        if len(steps) > MAX_STEPS:
            raise tools.ToolError("at most %d steps in one call" % MAX_STEPS)
        clean = []
        for i, s in enumerate(steps):
            if not isinstance(s, dict) or str(s.get("action") or "") not in STEP_ACTIONS:
                raise tools.ToolError("step %d: action must be one of %s" % (i + 1, ", ".join(STEP_ACTIONS)))
            clean.append(dict(s))
        st = phone_fast._state(ctx)
        done, screen = [], ""
        for i, s in enumerate(clean):
            if ctx.cancel is not None and ctx.cancel.is_set():
                raise tools.ToolError("cancelled")
            act = s.pop("action")
            if act == "open_app" and s.get("name"):
                s["name"] = phone_fast.app_name(s["name"])
            try:
                res = phone.call(act, **s)
                if not res.get("ok", True):
                    raise phone.PhoneError(res.get("error") or res.get("text") or "failed")
            except phone.PhoneError as e:
                screen = phone_fast.observe("tap", {})
                _keep_screen(ctx, screen)
                return ("Stopped at step %d of %d (%s %s): %s\nDone before it: %s\n\nScreen now:\n%s\nContinue from "
                        "this screen." % (i + 1, len(clean), act, json.dumps(s, ensure_ascii=False), e,
                                          "; ".join(done) or "nothing", tools.clip(screen, 7000))), \
                    {"steps": i, "done": False}
            done.append("%s %s" % (act, res.get("text") or ""))
            st["log"].append((act, dict(s, action=act), True))
            screen = str(res.get("screen") or "") or (phone_fast.observe(act, s) if act in ("open_app", "open_url")
                                                      else "")
        if not screen:
            screen = phone_fast.observe("tap", {})
        _keep_screen(ctx, screen)
        return ("Done, %d steps: %s\n\nScreen now:\n%s" % (len(done), "; ".join(done), tools.clip(screen, 7000))), \
            {"steps": len(done), "done": True}
