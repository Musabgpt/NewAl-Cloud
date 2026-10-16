package dev.newal.code.lite;

import android.app.Activity;
import android.content.Context;
import android.content.res.Configuration;
import android.graphics.Color;
import android.os.SystemClock;
import android.text.InputType;
import android.text.TextUtils;
import android.util.Log;
import android.util.TypedValue;
import android.view.Gravity;
import android.view.View;
import android.view.inputmethod.EditorInfo;
import android.view.inputmethod.InputMethodManager;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.TextView;
import android.widget.Toast;

import org.json.JSONObject;
import org.mozilla.geckoview.GeckoResult;
import org.mozilla.geckoview.GeckoRuntime;
import org.mozilla.geckoview.GeckoSession;
import org.mozilla.geckoview.GeckoView;
import org.mozilla.geckoview.WebExtension;

import java.lang.ref.WeakReference;
import java.util.HashMap;
import java.util.Map;

/**
 * The browser inside the chat: a GeckoView (Firefox's engine) in a pane above the conversation. The agent opens and
 * reads pages there (browser_open, browser_read, browser_close, through PhoneServer); the user sees the same page and
 * can tap, type and enter an address in it. Its sign-ins stay in its own profile, apart from the phone's browsers.
 *
 * The page is read by a built-in extension (assets/musab_browser): its content script numbers the page's links and
 * fields and answers over a native port. What it reads is page data for the model, never instructions.
 */
final class BrowserPane {
    private static final String TAG = "NewAlCode";
    // Bump the extension's version in its manifest.json whenever content.js changes: ensureBuiltIn reinstalls on it.
    private static final String EXTENSION = "resource://android/assets/musab_browser/";
    private static final String EXTENSION_ID = "browser@musabai.newal";
    private static final String NATIVE_APP = "musab";
    private static final long EXTENSION_TIMEOUT = 10_000, LOAD_TIMEOUT = 30_000, CONNECT_TIMEOUT = 5_000,
            SNAPSHOT_TIMEOUT = 10_000;

    // The engine and the page: one for the app's process (Gecko may be started only once).
    private static final Object LOCK = new Object();
    private static GeckoRuntime runtime;
    private static GeckoSession session;
    private static WebExtension extension;              // guarded by LOCK
    private static WebExtension.Port port;              // the shown page's reader; guarded by LOCK
    private static boolean loading, loadFailed, canGoBack;
    private static String url = "", title = "", unavailable = "";
    private static int nextId;
    private static final Map<Integer, JSONObject[]> replies = new HashMap<>();

    // The pane in MainActivity (main thread only).
    private static WeakReference<Activity> owner = new WeakReference<>(null);
    private static LinearLayout pane;
    private static GeckoView view;
    private static EditText address;
    private static boolean shown;

    private BrowserPane() {
    }

    // ------------------------------------------------------------------ the agent's actions (PhoneServer's thread)

    static JSONObject handle(Context ctx, JSONObject a) throws Exception {
        switch (a.optString("action")) {
            case "browser_open":
                return open(ctx, BrowserAddress.forAgent(a.optString("url")));
            case "browser_read":
                if (session == null) {
                    throw new IllegalStateException("no page is open: call browser_open first");
                }
                return page();
            case "browser_close":
                Phone.onMain(() -> {
                    show(false);
                    return null;
                });
                return Phone.ok("closed the browser pane (the page and its sign-ins stay)");
            default:
                throw new IllegalArgumentException("unknown browser action " + a.optString("action"));
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
            show(true);
            session.loadUri(target);
            return null;
        });
        boolean stopped = waitFor(() -> !loading, LOAD_TIMEOUT);
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
        JSONObject read = waitFor(() -> port != null, CONNECT_TIMEOUT) ? snapshot() : null;
        JSONObject out = read != null ? read : new JSONObject();
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

    private static JSONObject snapshot() throws Exception {
        final JSONObject[] box = new JSONObject[1];
        final int id = register(box);
        try {
            boolean sent = Phone.onMain(() -> {
                WebExtension.Port p;
                synchronized (LOCK) {
                    p = port;
                }
                if (p == null) {
                    return false;
                }
                p.postMessage(new JSONObject().put("type", "snapshot").put("id", id));
                return true;
            });
            if (!sent || !waitFor(() -> box[0] != null, SNAPSHOT_TIMEOUT)) {
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
            runtime = GeckoRuntime.create(ctx.getApplicationContext());
            GeckoSession s = new GeckoSession();
            s.setProgressDelegate(new GeckoSession.ProgressDelegate() {
                @Override
                public void onPageStart(GeckoSession g, String u) {
                    synchronized (LOCK) {
                        loading = true;
                        loadFailed = false;
                        url = u;
                        port = null;              // the new page's reader connects when it is ready
                        LOCK.notifyAll();
                    }
                    showAddress(u);
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

                /** A link that opens a new window opens here instead: the pane has one page. */
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

    private static final WebExtension.PortDelegate PORT = new WebExtension.PortDelegate() {
        @Override
        public void onPortMessage(Object message, WebExtension.Port p) {
            if (!(message instanceof JSONObject)) {
                return;
            }
            JSONObject m = (JSONObject) message;
            if (!"snapshot".equals(m.optString("type"))) {
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

    // ------------------------------------------------------------------ the pane (main thread)

    /** MainActivity's pane above the conversation: empty until the browser is first shown. */
    static void attach(Activity a, LinearLayout box) {
        owner = new WeakReference<>(a);
        pane = box;
        view = null;
        address = null;
        if (shown) {
            show(true);
        }
    }

    static void detach(Activity a) {
        if (owner.get() != a) {
            return;
        }
        if (view != null) {
            view.releaseSession();
        }
        view = null;
        address = null;
        pane = null;
        owner = new WeakReference<>(null);
    }

    static boolean visible() {
        return shown;
    }

    /** The globe button in the chat's top bar: "toggle", "show" or "hide". */
    static void command(String what) {
        show("toggle".equals(what) ? !shown : "show".equals(what));
    }

    /** The back key while the pane is shown: the page's previous page, else the pane closes. */
    static void back() {
        if (session != null && canGoBack) {
            session.goBack();
        } else {
            show(false);
        }
    }

    static void show(boolean on) {
        shown = on;
        Activity a = owner.get();
        if (pane == null || a == null) {
            return;                       // shown when MainActivity is back (attach)
        }
        if (on && !build(a)) {
            shown = false;
            Toast.makeText(a, unavailable, Toast.LENGTH_LONG).show();
            return;
        }
        pane.setVisibility(on ? View.VISIBLE : View.GONE);
        if (!on && address != null) {
            keyboard(a, address, false);
        }
    }

    private static boolean build(Activity a) {
        if (view != null) {
            return true;
        }
        if (!engine(a)) {
            return false;
        }
        boolean night = (a.getResources().getConfiguration().uiMode & Configuration.UI_MODE_NIGHT_MASK)
                == Configuration.UI_MODE_NIGHT_YES;
        int bg = night ? 0xff1e1e20 : Color.WHITE;
        int fg = night ? 0xffececf0 : 0xff222222;
        int faint = night ? 0xff8b8b95 : 0xff6b6b75;
        int line = night ? 0xff3a3a40 : 0xffdddddd;

        LinearLayout bar = new LinearLayout(a);
        bar.setOrientation(LinearLayout.HORIZONTAL);
        bar.setGravity(Gravity.CENTER_VERTICAL);
        bar.setBackgroundColor(bg);
        bar.setPadding(dp(a, 4), 0, dp(a, 4), 0);
        bar.addView(button(a, "‹", fg, v -> back()), new LinearLayout.LayoutParams(dp(a, 40), dp(a, 40)));

        address = new EditText(a);
        address.setSingleLine(true);
        address.setEllipsize(TextUtils.TruncateAt.MIDDLE);
        address.setTextSize(TypedValue.COMPLEX_UNIT_SP, 14);
        address.setTextColor(fg);
        address.setHintTextColor(faint);
        address.setHint(arabic(a) ? "عنوان أو بحث" : "Address or search");
        address.setInputType(InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_URI);
        address.setImeOptions(EditorInfo.IME_ACTION_GO);
        address.setSelectAllOnFocus(true);
        address.setBackground(null);
        address.setOnEditorActionListener((v, id, ev) -> {
            String target = BrowserAddress.forUser(v.getText().toString());
            if (!target.isEmpty() && session != null) {
                session.loadUri(target);
            }
            keyboard(a, address, false);
            v.clearFocus();
            return true;
        });
        bar.addView(address, new LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f));
        bar.addView(button(a, "⟳", fg, v -> {
            if (session != null) {
                session.reload();
            }
        }), new LinearLayout.LayoutParams(dp(a, 40), dp(a, 40)));
        bar.addView(button(a, "✕", fg, v -> show(false)), new LinearLayout.LayoutParams(dp(a, 40), dp(a, 40)));

        view = new GeckoView(a);
        view.setSession(session);

        View divider = new View(a);
        divider.setBackgroundColor(line);

        pane.removeAllViews();
        pane.addView(bar, new LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, dp(a, 44)));
        pane.addView(view, new LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, 0, 1f));
        pane.addView(divider, new LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, dp(a, 1)));
        synchronized (LOCK) {
            showAddress(url);
        }
        return true;
    }

    private static void showAddress(String u) {
        if (address != null && !address.hasFocus()) {
            address.setText(u == null || "about:blank".equals(u) ? "" : u);
        }
    }

    private static TextView button(Activity a, String label, int color, View.OnClickListener click) {
        TextView b = new TextView(a);
        b.setText(label);
        b.setTextColor(color);
        b.setTextSize(TypedValue.COMPLEX_UNIT_SP, 18);
        b.setGravity(Gravity.CENTER);
        TypedValue ripple = new TypedValue();
        if (a.getTheme().resolveAttribute(android.R.attr.selectableItemBackgroundBorderless, ripple, true)) {
            b.setBackgroundResource(ripple.resourceId);
        }
        b.setOnClickListener(click);
        return b;
    }

    private static void keyboard(Activity a, View v, boolean on) {
        InputMethodManager im = a.getSystemService(InputMethodManager.class);
        if (im != null && !on) {
            im.hideSoftInputFromWindow(v.getWindowToken(), 0);
        }
    }

    private static boolean arabic(Activity a) {
        return "ar".equals(a.getResources().getConfiguration().getLocales().get(0).getLanguage());
    }

    private static int dp(Activity a, int v) {
        return Math.round(v * a.getResources().getDisplayMetrics().density);
    }
}
