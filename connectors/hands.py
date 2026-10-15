"""The phone does more per call (item 7 of the research plan: Mobile-Agent-E's shortcuts and AutoDroid-V2's scripts
finish phone tasks in fewer model calls, each step still checked on the screen).

* send (text, item?): in an open chat, types the text into the message field and taps its Send button, then checks on
  the screen that the text left the field. One call instead of three (tap the field, type, tap Send).
* search (text, item?): inside an app, finds its search field (tapping the search icon first when only the icon
  shows), types the text and presses enter. One call instead of three or four.
* A tap on a text that is not on the screen scrolls the list down until it shows (up to 10 scrolls, stopping where the
  list ends) and taps it: one call instead of a failed tap and a swipe-and-look loop of model calls.

Every step goes through the phone tool as if the model had called it: it is logged, judged by the screen check and
learned into routines like any other action. A Send button is only a control named exactly so ("Send", "إرسال",
"Send message"): never "Send money". A search field is one that says it is one: search never types into a chat's
message field.
"""
import re

from . import phone_fast, tools

MARK = "\n\nScreen now:\n"
ITEM = re.compile(r"^\[(\d+)\]\s+(.*)$")
NOT_ON_SCREEN = "nothing on the screen says"
SCROLLS = 10
# matched on phone_fast._norm's folding (lower case, no marks, أ/ا, ة/ه, ى/ي, punctuation as spaces)
SEND = {"send", "send message", "send sms", "send mms", "send text", "ارسال", "ارسل", "ارسال الرساله",
        "ارسل الرساله", "بعت", "ابعت", "envoyer", "enviar", "invia", "senden", "gonder", "kirim", "отправить"}
SEARCH = {"search", "بحث", "ابحث", "find", "buscar", "chercher", "suche", "rechercher", "поиск"}
SUBMIT = SEARCH | {"go", "انتقال", "اذهب"}
MESSAGE = {"message", "messages", "رساله", "اكتب", "text", "mesaj", "сообщение"}
# (The phone tool's whole schema stays under 2000 characters: a phone's small model reads it at every thread's start.)
DOC = ("Use the Android phone this runs on: open_app (name: in any language, or the package), open_url (links, "
       "YouTube or web searches, local servers in Chrome), tap (item: a number from the latest screen, or text: "
       "scrolled to if further down), type (text into the focused field; tap it first), send (text: in an open "
       "chat, types it and taps Send), search (text: in an app, types into its search field and presses enter), "
       "swipe/scroll (direction), key (name: back, home, enter), settings (page), screen (the UI as numbered items), "
       "screenshot, alarm, timer, clipboard, notify, install_apk. Actions that change the screen return the new "
       "screen: read it there, not with screen. Reading and tapping need NewAl Code's accessibility service. Not "
       "for files or code.")


def listing(screen):
    """[(number, words, tags)] of a screen listing: "[7] Send · button, tap" -> (7, "Send", {"button", "tap"})."""
    out = []
    for line in str(screen or "").splitlines():
        m = ITEM.match(line.strip())
        if m:
            words, sep, tags = m.group(2).rpartition(" · ")
            if not sep:
                words, tags = m.group(2), ""
            out.append((int(m.group(1)), words.strip(), {t.strip() for t in tags.split(",") if t.strip()}))
    return out


def _has(words, vocabulary):
    """Whether one of the words (folded, with or without its article) is in the vocabulary."""
    w = str(words or "")
    if w.startswith("hint: "):
        w = w[6:]
    return any(x in vocabulary or phone_fast._bare(x) in vocabulary for x in phone_fast._norm(w).split())


def is_send(words):
    w = phone_fast._norm(words)
    return w in SEND or (w.startswith("send ") and any(x in w.split() for x in ("message", "sms", "mms"))) or \
        (w.startswith("ارسال ") and "رساله" in w)


def _shows(screen, text):
    want = phone_fast._norm(text)
    bare = phone_fast._bare(want)
    for _, words, _ in listing(screen):
        w = phone_fast._norm(words)
        if want and (want in w or bare in phone_fast._bare(w)):
            return True
    return False


def _text(out):
    return out[0] if isinstance(out, tuple) else str(out or "")


def _meta(out):
    return dict(out[1]) if isinstance(out, tuple) and isinstance(out[1], dict) else {}


class Hands:
    """One compound action: its steps go through the phone tool below (logged, checked) on one context."""

    def __init__(self, ctx, inner):
        self.ctx, self.inner = ctx, inner

    def call(self, action, **args):
        if self.ctx.cancel is not None and self.ctx.cancel.is_set():
            raise tools.ToolError("cancelled")
        return self.inner(self.ctx, action, **args)

    def read(self):
        return _text(self.call("screen"))

    def after(self, out):
        """The screen after a step: the one the app sent with it (phone_fast keeps it whole), else read now."""
        text = _text(out)
        if MARK not in text:
            return self.read()
        try:
            screen = phone_fast._state(self.ctx).get("screen")
        except AttributeError:
            screen = ""
        return screen or text[text.rfind(MARK) + len(MARK):]

    @staticmethod
    def result(message, screen, out, **meta):
        m = _meta(out)
        m.update(meta)
        return "%s%s%s" % (message, MARK, tools.clip(screen, 7000)), m

    # ---------------------------------------------------------------- send
    def send(self, text, item=None):
        text = str(text or "")
        if not text.strip():
            raise tools.ToolError("send needs text: the message to send")
        screen = self.read()
        field = self.message_field(listing(screen), item)
        out = self.call("type", text=text, item=field)
        screen = self.after(out)
        items = listing(screen)
        found = [n for n, words, tags in items if "tap" in tags and "field" not in tags and is_send(words)]
        button = ([n for n in found if n > field] or found or [None])[0]
        short = tools.clip(text, 80)
        if button is None:
            return self.result('Typed "%s" into [%d], but no Send button is on the screen to tap (it may be an icon '
                               'without a label): tap it by its number.' % (short, field), screen, out, sent=False)
        out = self.call("tap", item=button)
        screen = self.after(out)
        from . import finish
        if finish.field_with(screen, text):
            return self.result('Typed "%s" into [%d] and tapped [%d], but the text is still in the field: it was '
                               'not sent.' % (short, field, button), screen, out, sent=False)
        return self.result('Sent: typed "%s" into [%d] and tapped [%d] Send; the text left the field.'
                           % (short, field, button), screen, out, sent=True)

    @staticmethod
    def message_field(items, item):
        fields = [f for f in items if "field" in f[2]]
        if item:
            if not any(n == int(item) for n, _, _ in fields):
                raise tools.ToolError("item %s is not a text field on the screen: pass the message field's number"
                                      % item)
            return int(item)
        if not fields:
            raise tools.ToolError("no text field on this screen: open the chat first (send types into its message "
                                  "field)")
        if len(fields) == 1:
            return fields[0][0]
        for pick in ([f for f in fields if "focused" in f[2]], [f for f in fields if _has(f[1], MESSAGE)]):
            if len(pick) == 1:
                return pick[0][0]
        raise tools.ToolError("several text fields on this screen (%s): pass item, the message field's number"
                              % ", ".join("[%d]" % f[0] for f in fields))

    # ---------------------------------------------------------------- search
    def search(self, text, item=None):
        text = str(text or "")
        if not text.strip():
            raise tools.ToolError("search needs text: what to search for")
        screen = self.read()
        items = listing(screen)
        done, out = [], None
        field = self.search_field(items, item)
        if field is None:
            icon = next((n for n, words, tags in items if "tap" in tags and "field" not in tags
                         and _has(words, SEARCH)), None)
            if icon is None:
                raise tools.ToolError("no search field or search button on this screen: open the app (or its search "
                                      "page) first%s%s" % (MARK, tools.clip(screen, 3000)))
            out = self.call("tap", item=icon)
            done.append("tapped [%d] (search)" % icon)
            screen = self.after(out)
            items = listing(screen)
            field = self.search_field(items, None, focused_ok=True)
            if field is None:
                raise tools.ToolError("tapped [%d] (search), but no search field came up%s%s"
                                      % (icon, MARK, tools.clip(screen, 3000)))
        if not any(n == field and "focused" in tags for n, _, tags in items):
            out = self.call("tap", item=field)
            screen = self.after(out)
            items = listing(screen)
            field = next((n for n, _, tags in items if "field" in tags and "focused" in tags), field)
        out = self.call("type", text=text, item=field)
        done.append('typed "%s" into [%d]' % (tools.clip(text, 80), field))
        screen = self.after(out)
        try:
            out = self.call("key", name="enter")
            done.append("pressed enter")
        except tools.ToolError:
            go = next((n for n, words, tags in listing(screen) if "tap" in tags and "field" not in tags
                       and _has(words, SUBMIT)), None)
            if go is None:
                return self.result("Searched: %s, but enter did not go through and no search button shows: tap a "
                                   "suggestion or the search button." % "; ".join(done), screen, out, submitted=False)
            out = self.call("tap", item=go)
            done.append("tapped [%d] (search)" % go)
        screen = self.after(out)
        return self.result("Searched: %s." % "; ".join(done), screen, out, submitted=True)

    @staticmethod
    def search_field(items, item, focused_ok=False):
        """The search field: the one given, or one that says it searches; just after tapping the search icon, the
        focused field too. Never another field (a chat's message field is not a search field)."""
        fields = [f for f in items if "field" in f[2]]
        if item:
            if not any(n == int(item) for n, _, _ in fields):
                raise tools.ToolError("item %s is not a text field on the screen" % item)
            return int(item)
        named = [f[0] for f in fields if _has(f[1], SEARCH)]
        if named:
            return named[0]
        if focused_ok:
            focused = [f[0] for f in fields if "focused" in f[2]]
            if focused:
                return focused[0]
            if len(fields) == 1:
                return fields[0][0]
        return None

    # ---------------------------------------------------------------- tap, scrolling to its text
    def tap(self, args):
        try:
            return self.call("tap", **args)
        except tools.ToolError as e:
            if NOT_ON_SCREEN not in str(e):
                raise
            first = e
        screen = self.read()
        if not any("scrolls" in tags for _, _, tags in listing(screen)):
            raise first
        # the items themselves, numbers included ("Room 101" is not "Room 102"): the same after a scroll is the end
        last = [words for _, words, _ in listing(screen)]
        for n in range(1, SCROLLS + 1):
            out = self.call("scroll", direction="down")
            screen = self.after(out)
            if _shows(screen, args["text"]):
                out = self.call("tap", **args)
                return "Scrolled down %d time%s to find it. %s" % (n, "" if n == 1 else "s", _text(out)), _meta(out)
            now = [words for _, words, _ in listing(screen)]
            if now == last:
                break                                   # the list ends here
            last = now
        raise tools.ToolError('%s "%s", even after scrolling down to the end of the list%s%s'
                              % (NOT_ON_SCREEN, args["text"], MARK, tools.clip(screen, 3000)))


def wrap_phone():
    t = tools.REGISTRY.get("phone")
    if t is None or getattr(t.fn, "_hands", False):
        return
    inner = t.fn

    def phone(ctx, action, **args):
        action = str(action or "")
        hands = Hands(ctx, inner)
        if action == "send":
            return hands.send(args.get("text"), args.get("item"))
        if action == "search":
            return hands.search(args.get("text"), args.get("item"))
        if action == "tap" and args.get("text") and not args.get("item") and "x" not in args:
            return hands.tap(args)
        return inner(ctx, action, **args)
    # the layers inside stay known (phone_fast's _fast, vital's _vital): installing one again does not wrap it twice
    phone.__dict__.update({k: v for k, v in getattr(inner, "__dict__", {}).items() if k.startswith("_")})
    phone._hands = True
    t.fn = phone
    t.description = DOC
    action = dict(t.params.get("action") or {})
    action["enum"] = list(action.get("enum") or []) + [a for a in ("send", "search") if a not in (action.get("enum")
                                                                                                  or [])]
    t.params = dict(t.params, action=action)


def install():
    wrap_phone()
