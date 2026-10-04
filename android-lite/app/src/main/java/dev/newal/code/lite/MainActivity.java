package dev.newal.code.lite;

import android.app.Activity;
import android.content.Intent;
import android.content.res.Configuration;
import android.graphics.Color;
import android.graphics.Insets;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.speech.RecognizerIntent;
import android.text.Html;
import android.view.View;
import android.view.ViewGroup;
import android.view.Window;
import android.view.WindowInsets;
import android.view.WindowInsetsController;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.FrameLayout;

import java.net.HttpURLConnection;
import java.net.URL;

/** NewAl Code's interface (the same web app as on a computer) in a WebView, once the service has started it. */
public class MainActivity extends Activity {
    static final int PICK_MODEL = 7;
    static final int VOICE = 8;
    static final int FILES = 9;
    private android.webkit.ValueCallback<Uri[]> files;
    private static final String HOME = "http://127.0.0.1:" + Setup.PORT + "/";
    private FrameLayout root;
    private WebView web;
    private WebBridge bridge;
    private String key;
    private volatile int waitGeneration;

    @Override
    protected void onCreate(Bundle state) {
        super.onCreate(state);
        root = new FrameLayout(this);
        web = new WebView(this);
        root.addView(web, new FrameLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.MATCH_PARENT));
        setContentView(root);
        boolean night = (getResources().getConfiguration().uiMode & Configuration.UI_MODE_NIGHT_MASK)
                == Configuration.UI_MODE_NIGHT_YES;
        betweenBars();
        bars(night ? 0xff1e1e20 : Color.WHITE, night);
        WebSettings s = web.getSettings();
        s.setJavaScriptEnabled(true);
        s.setDomStorageEnabled(true);
        web.setWebChromeClient(new WebChromeClient() {           // confirm() and alert() dialogs, and:
            /** The page's file inputs ("Attach an image"): Android's picker (a WebView has none of its own). */
            @Override
            public boolean onShowFileChooser(WebView view, android.webkit.ValueCallback<Uri[]> callback,
                                             FileChooserParams params) {
                if (files != null) {
                    files.onReceiveValue(null);
                }
                files = callback;
                Intent pick = params.createIntent();
                pick.putExtra(Intent.EXTRA_ALLOW_MULTIPLE, params.getMode() == FileChooserParams.MODE_OPEN_MULTIPLE);
                try {
                    startActivityForResult(Intent.createChooser(pick, "NewAl Code"), FILES);
                    return true;
                } catch (Exception e) {
                    files = null;
                    return false;
                }
            }
        });
        key = new Setup(this).key();
        bridge = new WebBridge(this, web, key);
        web.addJavascriptInterface(bridge, "NewAlPhone");
        web.setWebViewClient(new WebViewClient() {
            @Override
            public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
                Uri u = request.getUrl();
                if ("newal".equals(u.getScheme()) && "retry".equals(u.getHost())) {
                    startAgent(true);
                    return true;
                }
                if ("127.0.0.1".equals(u.getHost())) {
                    return false;
                }
                try {
                    startActivity(new Intent(Intent.ACTION_VIEW, u));   // GitHub, Hugging Face: the browser
                } catch (Exception ignored) {
                }
                return true;
            }
        });
        page("جارٍ تشغيل NewAl Code…", "يتم تجهيز Python وبدء التطبيق. قد يستغرق التشغيل الأول حتى دقيقتين.", night);
        if (Build.VERSION.SDK_INT >= 33) {
            requestPermissions(new String[] {"android.permission.POST_NOTIFICATIONS"}, 1);
        }
        startAgent(false);
        Shared.from(this, getIntent(), this::tellShared);
        Shared.shortcut(getIntent(), this::tellShared);
    }

    /** Shared from another app while NewAl Code runs (the activity is single-task). */
    @Override
    protected void onNewIntent(Intent i) {
        super.onNewIntent(i);
        setIntent(i);
        if (i.getData() != null && "musabai".equals(i.getData().getScheme()) && "connectors".equals(i.getData().getHost())) {
            web.evaluateJavascript("window.openMusabConnectors && window.openMusabConnectors()", null);
            return;
        }
        Shared.from(this, i, this::tellShared);
        Shared.shortcut(i, this::tellShared);
    }

    private void tellShared() {
        web.evaluateJavascript("window.onPhoneShared && window.onPhoneShared()", null);
    }

    /**
     * The page between the status bar (and a camera cutout) and the navigation bar or the keyboard. Android 15 draws
     * apps under those bars, so from Android 11 on the app lays itself out that way and pads the page; Android 8 to
     * 10 stop the window at the bars, and adjustResize at the keyboard.
     */
    private void betweenBars() {
        if (Build.VERSION.SDK_INT < 30) {
            return;
        }
        getWindow().setDecorFitsSystemWindows(false);
        root.setOnApplyWindowInsetsListener((v, insets) -> {
            Insets bars = insets.getInsets(WindowInsets.Type.systemBars() | WindowInsets.Type.displayCutout());
            Insets ime = insets.getInsets(WindowInsets.Type.ime());
            v.setPadding(bars.left, bars.top, bars.right, Math.max(bars.bottom, ime.bottom));
            return WindowInsets.CONSUMED;
        });
        root.requestApplyInsets();
    }

    /** The status and navigation bars in the page's colour, with icons that show on it (the page tells its colour). */
    void bars(int color, boolean dark) {
        root.setBackgroundColor(color);
        web.setBackgroundColor(color);
        Window w = getWindow();
        if (Build.VERSION.SDK_INT >= 30) {
            w.setStatusBarColor(Color.TRANSPARENT);
            w.setNavigationBarColor(Color.TRANSPARENT);
            WindowInsetsController c = w.getInsetsController();
            int light = WindowInsetsController.APPEARANCE_LIGHT_STATUS_BARS
                    | WindowInsetsController.APPEARANCE_LIGHT_NAVIGATION_BARS;
            if (c != null) {
                c.setSystemBarsAppearance(dark ? 0 : light, light);
            }
        } else {
            w.setStatusBarColor(color);
            w.setNavigationBarColor(color);
            View d = w.getDecorView();
            int light = View.SYSTEM_UI_FLAG_LIGHT_STATUS_BAR | View.SYSTEM_UI_FLAG_LIGHT_NAVIGATION_BAR;
            int flags = d.getSystemUiVisibility();
            d.setSystemUiVisibility(dark ? flags & ~light : flags | light);
        }
    }

    private void startAgent(boolean retry) {
        boolean night = (getResources().getConfiguration().uiMode & Configuration.UI_MODE_NIGHT_MASK)
                == Configuration.UI_MODE_NIGHT_YES;
        page("جارٍ تشغيل NewAl Code…", "يتم تجهيز Python وبدء التطبيق. قد يستغرق التشغيل الأول حتى دقيقتين.", night);
        Intent service = new Intent(this, AgentService.class);
        if (retry) service.setAction(AgentService.RETRY);
        // Do not show an error left by a previous failed service invocation.
        AgentService.error = "";
        startForegroundService(service);
        waitForServer();
    }

    private void waitForServer() {
        final int generation = ++waitGeneration;
        new Thread(() -> {
            long deadline = android.os.SystemClock.elapsedRealtime() + 120_000;
            while (generation == waitGeneration && android.os.SystemClock.elapsedRealtime() < deadline) {
                if (up(key)) {
                    runOnUiThread(() -> {
                        if (generation != waitGeneration || isFinishing() || isDestroyed()) return;
                        Uri data = getIntent().getData();
                        boolean connections = data != null && "musabai".equals(data.getScheme())
                                && "connectors".equals(data.getHost());
                        web.loadUrl(HOME + "?key=" + Uri.encode(key) + (connections ? "&connections=1" : ""));
                    });
                    return;
                }
                if (!AgentService.error.isEmpty()) break;
                try { Thread.sleep(250); }
                catch (InterruptedException e) { return; }
            }
            if (generation != waitGeneration) return;
            String why = AgentService.error.isEmpty()
                    ? "لم يستجب التطبيق خلال دقيقتين. اضغط إعادة المحاولة لتشغيله مجددًا."
                    : AgentService.error;
            String log = new Setup(this).logTail();
            if (!log.isEmpty()) why += "\n\n" + log;
            final String detail = why;
            boolean night = (getResources().getConfiguration().uiMode & Configuration.UI_MODE_NIGHT_MASK)
                    == Configuration.UI_MODE_NIGHT_YES;
            runOnUiThread(() -> {
                if (generation == waitGeneration && !isFinishing() && !isDestroyed())
                    page("تعذّر تشغيل NewAl Code", detail, night, true);
            });
        }, "newal-wait").start();
    }

    private static boolean up(String key) {
        HttpURLConnection c = null;
        try {
            c = (HttpURLConnection) new URL(HOME + "api/health").openConnection();
            c.setRequestProperty("X-NewAl-Key", key);
            c.setInstanceFollowRedirects(false);
            c.setConnectTimeout(500);
            c.setReadTimeout(500);
            return c.getResponseCode() == 200;
        } catch (Exception e) { return false; }
        finally { if (c != null) c.disconnect(); }
    }

    @Override
    protected void onDestroy() {
        ++waitGeneration;
        super.onDestroy();
    }

    private void page(String title, String text, boolean night) {
        page(title, text, night, false);
    }

    private void page(String title, String text, boolean night, boolean retry) {
        String html = "<html><head><meta name='viewport' content='width=device-width,initial-scale=1'></head>"
                + "<body style='font-family:sans-serif;padding:24px;margin:0;background:" + (night ? "#1e1e20" : "#fff")
                + ";color:" + (night ? "#ececf0" : "#222") + "'><h2>" + Html.escapeHtml(title)
                + "</h2><pre style='white-space:pre-wrap;color:" + (night ? "#a9a9b2" : "#555") + "'>"
                + Html.escapeHtml(text) + "</pre>"
                + (retry ? "<a href='newal://retry' style='display:inline-block;padding:14px 24px;background:#90d8b0;color:#10141d;border-radius:12px;text-decoration:none'>إعادة المحاولة</a>" : "")
                + "</body></html>";
        web.loadDataWithBaseURL(null, html, "text/html", "utf-8", null);
    }

    @Override
    protected void onPause() {
        super.onPause();
        Access.paused();
    }

    @Override
    protected void onResume() {
        super.onResume();
        Access.resumed(this);
    }

    @Override
    public void onRequestPermissionsResult(int request, String[] permissions, int[] results) {
        super.onRequestPermissionsResult(request, permissions, results);
        Access.answered(this, request);
    }

    /** The full-access walk is over: the page hears what is on now. */
    void accessDone() {
        String js = "window.onPhoneAccess && window.onPhoneAccess(" + bridge.status() + ")";
        runOnUiThread(() -> web.evaluateJavascript(js, null));
    }

    /** A GGUF file the user picked (the Models page's "Copy a GGUF into the app"): copied into the models folder. */
    @Override
    protected void onActivityResult(int request, int result, Intent data) {
        super.onActivityResult(request, result, data);
        if (request == PICK_MODEL && result == RESULT_OK && data != null && data.getData() != null) {
            ModelImport.start(this, web, data.getData());
        }
        if (request == FILES && files != null) {
            Uri[] picked = null;
            if (result == RESULT_OK && data != null) {
                if (data.getClipData() != null) {
                    picked = new Uri[data.getClipData().getItemCount()];
                    for (int k = 0; k < picked.length; k++) {
                        picked[k] = data.getClipData().getItemAt(k).getUri();
                    }
                } else if (data.getData() != null) {
                    picked = new Uri[] {data.getData()};
                }
            }
            files.onReceiveValue(picked);
            files = null;
        }
        if (request == VOICE && result == RESULT_OK && data != null) {
            java.util.ArrayList<String> said = data.getStringArrayListExtra(RecognizerIntent.EXTRA_RESULTS);
            if (said != null && !said.isEmpty()) {
                web.evaluateJavascript("window.onPhoneVoice && window.onPhoneVoice("
                        + org.json.JSONObject.quote(said.get(0)) + ")", null);
            }
        }
    }

    @Override
    public void onBackPressed() {
        if (web.canGoBack()) {
            web.goBack();
        } else {
            moveTaskToBack(true);        // keep working in the background (the service stays)
        }
    }
}
