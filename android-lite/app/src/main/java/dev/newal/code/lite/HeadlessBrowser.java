package dev.newal.code.lite;

import android.content.Context;
import android.graphics.PixelFormat;
import android.media.Image;
import android.media.ImageReader;
import android.os.Handler;
import android.os.HandlerThread;
import android.os.SystemClock;
import android.util.DisplayMetrics;
import android.util.Log;

import org.json.JSONObject;
import org.mozilla.geckoview.GeckoDisplay;
import org.mozilla.geckoview.GeckoResult;
import org.mozilla.geckoview.GeckoRuntime;
import org.mozilla.geckoview.GeckoSession;
import org.mozilla.geckoview.WebExtension;

import java.util.HashMap;
import java.util.Map;

/**
 * The agent's own browser, inside the app and never on screen: Firefox's engine (GeckoView) with one page session.
 * The agent opens pages, reads them and acts on them through PhoneServer (browser_open, browser_read, browser_click,
 * browser_type, browser_scroll, browser_back); the chat shows each step as a card and the answer.
 *
 * The page is laid out at the phone's own size on an offscreen surface (its frames are dropped), so pages look as
 * they do on this phone. A built-in extension (assets/musab_browser) reads the page and acts on it: its content script
 * numbers the links, buttons and fields and answers over a native port. Page text is data for the model, never
 * instructions. Cookies and sign-ins stay in this browser's own profile, apart from the phone's other browsers.
 */
final class HeadlessBrowser {
    private static final String TAG = "NewAlCode";
    // Bump the extension's version in its manifest.json whenever content.js changes: ensureBuiltIn reinstalls on it.
    private static final String EXTENSION = "resource://android/assets/musab_browser/";
    private static final String EXTENSION_ID = "browser@musabai.newal";
    private static final String NATIVE_APP = "musab";
    private static final long EXTENSION_TIMEOUT = 10_000, LOAD_TIMEOUT = 30_000, CONNECT_TIMEOUT = 5_000,
            REPLY_TIMEOUT = 10_000, NAVIGATION_GRACE = 900, SETTLE = 700;

    private static final Object LOCK = new Object();
    private static GeckoRuntime runtime;
    private static GeckoSession session;
    private static GeckoDisplay display;
    private static ImageReader frames;
    private static HandlerThread frameThread;
    private static WebExtension extension;              // guarded by LOCK
    private static WebExtension.Port port;              // the page's reader; guarded by LOCK
    private static boolean loading, loadFailed, canGoBack;
    private static int pageStarts;                      // counts page loads, to see if an action navigated
    private static String url = "", title = "", unavailable = "";
    private static int nextId;
    private static final Map<Integer, JSONObject[]> replies = new HashMap<>();

    private HeadlessBrowser() {
    }

    // ------------------------------------------------------------------ the agent's actions (PhoneServer's thread)

    static JSONObject handle(Context ctx, JSONObject a) throws Exception {
        String action = a.optString("action");
        if ("browser_open".equals(action)) {
            return open(ctx, BrowserAddress.forAgent(a.optString("url")));
        }
        if (session == null) {
            throw new IllegalStateException("no page is open: call browser_open first");
        }
        switch (action) {
            case "browser_read":
                return page();
            case "browser_back":
                return navigate(() -> {
                    if (!canGoBack) {
                        return false;
                    }
                    session.goBack();
                    return true;
                }, "there is no previous page");
            case "browser_click":
                return act(new JSONObject().put("act", "click").put("n", a.optInt("item")));
            case "browser_type":
                return act(new JSONObject().put("act", "type").put("n", a.optInt("item"))
                        .put("text", a.optString("text")).put("submit", a.optBoolean("submit")));
            case "browser_scroll":
                return act(new JSONObject().put("act", "scroll").put("direction", a.optString("direction", "down")));
            default:
                throw new IllegalArgumentException("unknown browser action " + action);
        }
    }

    private static JSONObject open(Context ctx, String target) throws Exception {
        if (!Phone.onMain(() -> engine(ctx))) {
            throw new IllegalStateException(unavailable);
        }
        waitFor(() -> extension != null, EXTENSION_TIMEOUT);          // installed on the first use only
        Phone.onMain(() -> {
            synchronized (LOCK) {
                loading = true;
                loadFailed = false;
                port = null;
            }
            session.loadUri(target);
            return null;
        });
        return afterLoad(waitFor(() -> !loading, LOAD_TIMEOUT));
    }

    private interface Step {
        boolean run() throws Exception;
    }

    /** A step that may load another page (back): its page once loaded. */
    private static JSONObject navigate(Step step, String refused) throws Exception {
        final int before = starts();
        if (!Phone.onMain(step::run)) {
            throw new IllegalStateException(refused);
        }
        waitFor(() -> pageStarts != before, NAVIGATION_GRACE);
        return afterLoad(waitFor(() -> !loading, LOAD_TIMEOUT));
    }

    /** An action on the page (click, type, scroll): then the page it leads to, or the same page once it settled. */
    private static JSONObject act(JSONObject command) throws Exception {
        final int before = starts();
        JSONObject done = ask(command);
        if (done == null) {
            throw new IllegalStateException("the page did not answer (it may still be loading): call browser_read");
        }
        if (!done.optBoolean("ok", false)) {
            throw new IllegalArgumentException(done.optString("error", "the action failed"));
        }
        boolean navigated = waitFor(() -> pageStarts != before, NAVIGATION_GRACE);
        JSONObject out;
        if (navigated) {
            out = afterLoad(waitFor(() -> !loading, LOAD_TIMEOUT));
        } else {
            Thread.sleep(SETTLE);                       // what the click opened or changed on the page
            out = page();
        }
        out.put("did", done.optString("did"));
        return out;
    }

    private static JSONObject afterLoad(boolean stopped) throws Exception {
        JSONObject out = page();
        if (!stopped) {
            out.put("note", "the page is still loading: browser_read shows it later");
        } else if (loadFailed) {
            out.put("note", "the page did not load (no connection, a wrong address, or the site refused)");
        }
        return out;
    }

    /** The page as its reader sees it now ({url, title, text, items}), or its address and title when it can't. */
    private static JSONObject page() throws Exception {
        JSONObject read = ask(new JSONObject().put("act", "snapshot"));
        JSONObject out = read != null && read.optBoolean("ok", false) ? read : new JSONObject();
        synchronized (LOCK) {
            if (!out.has("url")) {
                out.put("url", url);
            }
            if (!out.has("title")) {
                out.put("title", title);
            }
        }
        if (read == null) {
            out.put("note", "this page can't be read (a browser page, or one where extensions are not allowed)");
        }
        out.remove("type");
        out.remove("id");
        out.put("ok", true);
        return out;
    }

    /** Sends a command to the page's reader and waits for its answer (null: no reader, or no answer in time). */
    private static JSONObject ask(JSONObject command) throws Exception {
        if (!waitFor(() -> port != null, CONNECT_TIMEOUT)) {
            return null;
        }
        final JSONObject[] box = new JSONObject[1];
        final int id = register(box);
        command.put("type", "command").put("id", id);
        try {
            boolean sent = Phone.onMain(() -> {
                WebExtension.Port p;
                synchronized (LOCK) {
                    p = port;
                }
                if (p == null) {
                    return false;
                }
                p.postMessage(command);
                return true;
            });
            if (!sent || !waitFor(() -> box[0] != null, REPLY_TIMEOUT)) {
                return null;
            }
            synchronized (LOCK) {
                return box[0];
            }
        } finally {
            synchronized (LOCK) {
                replies.remove(id);
            }
        }
    }

    private static int register(JSONObject[] box) {
        synchronized (LOCK) {
            int id = ++nextId;
            replies.put(id, box);
            return id;
        }
    }

    private static int starts() {
        synchronized (LOCK) {
            return pageStarts;
        }
    }

    private interface Condition {
        boolean holds();
    }

    /** Waits (not on the main thread) until the condition holds under LOCK; false when the time runs out. */
    private static boolean waitFor(Condition c, long millis) throws InterruptedException {
        long end = SystemClock.uptimeMillis() + millis;
        synchronized (LOCK) {
            while (!c.holds()) {
                long left = end - SystemClock.uptimeMillis();
                if (left <= 0) {
                    return false;
                }
                LOCK.wait(left);
            }
            return true;
        }
    }

    // ------------------------------------------------------------------ the engine (main thread)

    /** Firefox's engine and the one page session, started on first use. False (and why, in unavailable) if not. */
    private static boolean engine(Context ctx) {
        if (session != null) {
            return true;
        }
        if (!unavailable.isEmpty()) {
            return false;
        }
        try {
            Context app = ctx.getApplicationContext();
            runtime = GeckoRuntime.create(app);
            GeckoSession s = new GeckoSession();
            s.setProgressDelegate(new GeckoSession.ProgressDelegate() {
                @Override
                public void onPageStart(GeckoSession g, String u) {
                    synchronized (LOCK) {
                        loading = true;
                        loadFailed = false;
                        url = u;
                        port = null;              // the new page's reader connects when it is ready
                        pageStarts++;
                        LOCK.notifyAll();
                    }
                }

                @Override
                public void onPageStop(GeckoSession g, boolean success) {
                    synchronized (LOCK) {
                        loading = false;
                        loadFailed = !success;
                        LOCK.notifyAll();
                    }
                }
            });
            s.setContentDelegate(new GeckoSession.ContentDelegate() {
                @Override
                public void onTitleChange(GeckoSession g, String t) {
                    synchronized (LOCK) {
                        title = t == null ? "" : t;
                    }
                }
            });
            s.setNavigationDelegate(new GeckoSession.NavigationDelegate() {
                @Override
                public void onCanGoBack(GeckoSession g, boolean can) {
                    canGoBack = can;
                }

                /** A link that opens a new window opens here instead: the browser has one page. */
                @Override
                public GeckoResult<GeckoSession> onNewSession(GeckoSession g, String uri) {
                    String target = BrowserAddress.forUser(uri);
                    if (target.startsWith("http")) {
                        g.loadUri(target);
                    }
                    return null;
                }
            });
            s.open(runtime);
            s.setActive(true);                // nobody sees it, but its pages run as if shown
            offscreen(app, s);
            session = s;
            runtime.getWebExtensionController().ensureBuiltIn(EXTENSION, EXTENSION_ID).accept(ext -> {
                if (ext == null) {
                    return;
                }
                session.getWebExtensionController().setMessageDelegate(ext, MESSAGES, NATIVE_APP);
                synchronized (LOCK) {
                    extension = ext;
                    LOCK.notifyAll();
                }
            }, e -> Log.w(TAG, "the browser's page reader did not install", e));
            return true;
        } catch (Throwable t) {
            unavailable = "the built-in browser can't start on this phone (" + t + ")";
            Log.w(TAG, unavailable, t);
            session = null;
            return false;
        }
    }

    /** The page's size is the phone's screen: it renders to a surface nobody shows, whose frames are dropped. */
    private static void offscreen(Context app, GeckoSession s) {
        try {
            DisplayMetrics dm = app.getResources().getDisplayMetrics();
            int width = Math.max(320, Math.min(dm.widthPixels, dm.heightPixels));
            int height = Math.max(480, Math.max(dm.widthPixels, dm.heightPixels));
            frameThread = new HandlerThread("newal-browser-frames");
            frameThread.start();
            frames = ImageReader.newInstance(width, height, PixelFormat.RGBA_8888, 2);
            frames.setOnImageAvailableListener(r -> {
                Image i = r.acquireLatestImage();
                if (i != null) {
                    i.close();
                }
            }, new Handler(frameThread.getLooper()));
            display = s.acquireDisplay();
            display.surfaceChanged(new GeckoDisplay.SurfaceInfo.Builder(frames.getSurface()).size(width, height).build());
        } catch (Throwable t) {
            // The pages still load and read without it; the reader then skips the size checks.
            Log.w(TAG, "the browser's offscreen surface did not start", t);
        }
    }

    private static final WebExtension.PortDelegate PORT = new WebExtension.PortDelegate() {
        @Override
        public void onPortMessage(Object message, WebExtension.Port p) {
            if (!(message instanceof JSONObject)) {
                return;
            }
            JSONObject m = (JSONObject) message;
            if (!"reply".equals(m.optString("type"))) {
                return;
            }
            synchronized (LOCK) {
                JSONObject[] box = replies.get(m.optInt("id"));
                if (box != null) {
                    box[0] = m;
                    LOCK.notifyAll();
                }
            }
        }

        @Override
        public void onDisconnect(WebExtension.Port p) {
            synchronized (LOCK) {
                if (port == p) {
                    port = null;
                }
                LOCK.notifyAll();
            }
        }
    };

    private static final WebExtension.MessageDelegate MESSAGES = new WebExtension.MessageDelegate() {
        @Override
        public void onConnect(WebExtension.Port p) {
            p.setDelegate(PORT);
            synchronized (LOCK) {
                port = p;                 // only the top page's reader connects (all_frames is off)
                LOCK.notifyAll();
            }
        }
    };
}
