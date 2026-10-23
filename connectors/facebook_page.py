"""A Facebook Page, connected in the app (Connections > Facebook Page): posts go up through Facebook's API, with no app
opening, the screen off and the phone locked. Only Pages: Facebook lets no app post on a person's profile.

The Page's token stays in the app's Keystore vault (FacebookPage.java): these tools ask the app to post or to list the
Page's latest posts, and never see it. They are connector operations of the provider "facebook", so they are offered
while the Page is connected (connectors.names), lean mode included, and a scheduled task about Facebook runs through
them instead of on the screen (schedule.py).
"""
from . import tools

PROVIDER = "facebook"
OPS = {"facebook_page_post": ("POST", "feed"), "facebook_page_recent": ("GET", "posts")}


def _native(op, **args):
    from . import connectors, phone
    try:
        return connectors.native(op, provider=PROVIDER, **args).get("data") or {}
    except phone.PhoneError as e:
        raise tools.ToolError(str(e))


def install():
    from . import connectors
    for name, (method, route) in OPS.items():
        connectors.OPERATIONS[name] = (PROVIDER, method, route)

    @tools.tool("facebook_page_post",
                "Publish a post on the user's connected Facebook Page, through Facebook's API: no app opens and the "
                "screen can stay off. message: the post's text; link: an optional web address shown with it. First "
                "read the Page's latest posts (facebook_page_recent) and never publish the same text again. Returns "
                "the new post's address.",
                {"message": tools._s("the post's text"),
                 "link": tools._s("optional: a web address (https://...) to share with it")},
                ["message"], "connector_write")
    def t_post(ctx, message, link=""):
        d = _native("post", message=str(message or ""), link=str(link or ""))
        where = d.get("url") or d.get("id") or ""
        return "Posted on %s: %s" % (d.get("page") or "the Facebook Page", where), \
            {"connector": PROVIDER, "post": d.get("id"), "url": d.get("url")}

    @tools.tool("facebook_page_recent",
                "The connected Facebook Page's latest posts (time, text, address): what is already posted, so a new "
                "post says something new.",
                {"limit": tools._i("how many, 1-50 (default 10)")},
                [], "read")
    def t_recent(ctx, limit=10):
        d = _native("recent", limit=int(limit or 10))
        posts = d.get("posts") or []
        if not posts:
            return "The Page %s has no posts yet." % (d.get("page") or ""), {"connector": PROVIDER, "posts": 0}
        lines = ["%s  %s%s" % (p.get("time", "")[:16].replace("T", " "), (p.get("message") or "(no text)")[:500],
                               ("  " + p["url"]) if p.get("url") else "") for p in posts]
        return ("Latest posts on %s (newest first):\n%s" % (d.get("page") or "the Page", "\n".join(lines))), \
            {"connector": PROVIDER, "posts": len(posts)}
