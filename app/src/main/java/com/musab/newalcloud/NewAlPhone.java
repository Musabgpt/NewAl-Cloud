package com.musab.newalcloud;

import android.content.ClipData;
import android.content.ClipboardManager;
import android.content.Context;
import android.content.Intent;
import android.net.Uri;
import android.provider.Settings;
import android.webkit.JavascriptInterface;

import org.json.JSONObject;

final class NewAlPhone {
    private final MainActivity activity;
    private final WebBridge bridge;

    NewAlPhone(MainActivity activity, WebBridge bridge) {
        this.activity = activity;
        this.bridge = bridge;
    }

    @JavascriptInterface
    public String status() {
        try {
            JSONObject t = new JSONObject()
                    .put("installed", Termux.installed(activity))
                    .put("up", Termux.up())
                    .put("allowed", Termux.allowed(activity));
            return new JSONObject()
                    .put("sdk", android.os.Build.VERSION.SDK_INT)
                    .put("accessibility", false)
                    .put("termux", t)
                    .toString();
        } catch (Exception e) { return "{}"; }
    }

    @JavascriptInterface
    public void termuxSetup(String command) {
        ClipboardManager cm = (ClipboardManager) activity.getSystemService(Context.CLIPBOARD_SERVICE);
        cm.setPrimaryClip(ClipData.newPlainText("NewAl Cloud Termux setup", command));
        Termux.open(activity);
    }

    @JavascriptInterface
    public String termuxStart() {
        try {
            if (!Termux.installed(activity)) return "not-installed";
            if (!Termux.allowed(activity)) return "not-allowed";
            Termux.run(activity, "newal-termux start");
            return "started";
        } catch (Exception e) { return "error"; }
    }

    @JavascriptInterface
    public void termuxAllow() {
        try {
            Intent i = new Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS,
                    Uri.parse("package:" + activity.getPackageName()));
            activity.startActivity(i);
        } catch (Exception ignored) {}
    }

    @JavascriptInterface
    public void openAccessibilitySettings() {
        try { activity.startActivity(new Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS)); } catch (Exception ignored) {}
    }

    @JavascriptInterface
    public void openAppInfo() {
        termuxAllow();
    }

    @JavascriptInterface
    public void go(String where) {
        if ("termux".equals(where)) Termux.open(activity);
        else activity.js("location.reload()");
    }

    @JavascriptInterface
    public void allowStorage() {
        // The full coding workspace lives in Termux; no GGUF storage permission is needed.
    }
}
