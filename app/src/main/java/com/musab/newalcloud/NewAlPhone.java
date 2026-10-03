package com.musab.newalcloud;

import android.app.Activity;
import android.content.ClipData;
import android.content.ClipboardManager;
import android.content.Context;
import android.content.Intent;
import android.net.Uri;
import android.provider.Settings;
import android.webkit.JavascriptInterface;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.io.OutputStream;
import java.util.ArrayList;
import java.util.List;

final class NewAlPhone {
    private static final int PICK_FILES = 4101;
    private static final int PICK_FOLDER = 4102;
    private static final int CREATE_FILE = 4103;
    private final MainActivity activity;
    private final WebBridge bridge;
    private String pendingCreateContent = "";
    private String pendingCreateName = "";

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
        cm.setPrimaryClip(ClipData.newPlainText("MusabAI Termux setup", command));
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
    public void openAppInfo() { termuxAllow(); }

    @JavascriptInterface
    public void go(String where) {
        if ("termux".equals(where)) Termux.open(activity);
        else activity.js("location.reload()");
    }

    @JavascriptInterface
    public void allowStorage() { pickFiles(); }

    @JavascriptInterface
    public void openApp(String packageName, String fallbackUrl) {
        try {
            Intent i = packageName == null || packageName.isEmpty() ? null : activity.getPackageManager().getLaunchIntentForPackage(packageName);
            if (i != null) { i.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK); activity.startActivity(i); return; }
        } catch (Exception ignored) {}
        openUrl(fallbackUrl);
    }

    @JavascriptInterface
    public void openUrl(String url) {
        try {
            if (url == null || url.isEmpty()) return;
            activity.startActivity(new Intent(Intent.ACTION_VIEW, Uri.parse(url)));
        } catch (Exception ignored) {}
    }

    @JavascriptInterface
    public void shareText(String text) {
        try {
            Intent s = new Intent(Intent.ACTION_SEND);
            s.setType("text/plain");
            s.putExtra(Intent.EXTRA_TEXT, text == null ? "" : text);
            activity.startActivity(Intent.createChooser(s, "Share with…"));
        } catch (Exception ignored) {}
    }

    @JavascriptInterface
    public void pickFiles() {
        try {
            Intent i = new Intent(Intent.ACTION_OPEN_DOCUMENT);
            i.addCategory(Intent.CATEGORY_OPENABLE);
            i.setType("*/*");
            i.putExtra(Intent.EXTRA_ALLOW_MULTIPLE, true);
            i.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION | Intent.FLAG_GRANT_PERSISTABLE_URI_PERMISSION);
            activity.startActivityForResult(i, PICK_FILES);
        } catch (Exception ignored) {}
    }

    @JavascriptInterface
    public void pickFolder() {
        try {
            Intent i = new Intent(Intent.ACTION_OPEN_DOCUMENT_TREE);
            i.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION | Intent.FLAG_GRANT_WRITE_URI_PERMISSION | Intent.FLAG_GRANT_PERSISTABLE_URI_PERMISSION);
            activity.startActivityForResult(i, PICK_FOLDER);
        } catch (Exception ignored) {}
    }

    @JavascriptInterface
    public void createFile(String name, String mime, String content) {
        try {
            pendingCreateName = (name == null || name.isEmpty()) ? "musabai.txt" : name;
            pendingCreateContent = content == null ? "" : content;
            Intent i = new Intent(Intent.ACTION_CREATE_DOCUMENT);
            i.addCategory(Intent.CATEGORY_OPENABLE);
            i.setType((mime == null || mime.isEmpty()) ? "text/plain" : mime);
            i.putExtra(Intent.EXTRA_TITLE, pendingCreateName);
            i.addFlags(Intent.FLAG_GRANT_WRITE_URI_PERMISSION | Intent.FLAG_GRANT_READ_URI_PERMISSION);
            activity.startActivityForResult(i, CREATE_FILE);
        } catch (Exception ignored) {}
    }

    void handleActivityResult(int requestCode, int resultCode, Intent data) {
        if (resultCode != Activity.RESULT_OK || data == null) return;
        if (requestCode == PICK_FILES) handlePickedFiles(data);
        else if (requestCode == PICK_FOLDER) {
            Uri u = data.getData();
            try {
                activity.getContentResolver().takePersistableUriPermission(u, Intent.FLAG_GRANT_READ_URI_PERMISSION | Intent.FLAG_GRANT_WRITE_URI_PERMISSION);
            } catch (Exception ignored) {}
            activity.js("window.onNativeFiles&&window.onNativeFiles(" + JSONObject.quote(
                    "[{\"name\":\"Workspace folder\",\"size\":0,\"mime\":\"inode/directory\",\"uri\":"+JSONObject.quote(u.toString())+"}]") + ")");
        } else if (requestCode == CREATE_FILE) {
            Uri u = data.getData();
            try (OutputStream out = activity.getContentResolver().openOutputStream(u)) {
                if (out != null) out.write(pendingCreateContent.getBytes(java.nio.charset.StandardCharsets.UTF_8));
                activity.js("window.onNativeCreatedFile&&window.onNativeCreatedFile(" + JSONObject.quote(pendingCreateName) + ")");
            } catch (Exception e) {
                activity.js("window.onNativeCreatedFile&&window.onNativeCreatedFile(" + JSONObject.quote("Failed: "+e.getMessage()) + ")");
            } finally {
                pendingCreateContent = ""; pendingCreateName = "";
            }
        }
    }

    private void handlePickedFiles(Intent data) {
        try {
            List<Uri> uris = new ArrayList<>();
            if (data.getClipData() != null) {
                ClipData cd = data.getClipData();
                for (int i=0;i<cd.getItemCount();i++) uris.add(cd.getItemAt(i).getUri());
            } else if (data.getData() != null) uris.add(data.getData());
            JSONArray out = new JSONArray();
            for (Uri u : uris) {
                try { activity.getContentResolver().takePersistableUriPermission(u, Intent.FLAG_GRANT_READ_URI_PERMISSION); } catch (Exception ignored) {}
                JSONObject x = new JSONObject().put("uri", u.toString());
                String[] meta = nameAndMime(u);
                x.put("name", meta[0]).put("mime", meta[1]).put("size", sizeOf(u));
                String text = readSmallText(u, meta[0], meta[1]);
                if (!text.isEmpty()) x.put("text", text);
                out.put(x);
            }
            activity.js("window.onNativeFiles&&window.onNativeFiles(" + JSONObject.quote(out.toString()) + ")");
        } catch (Exception e) {
            activity.js("window.onNativeFiles&&window.onNativeFiles('[]')");
        }
    }

    private String[] nameAndMime(Uri u) {
        String name = "file";
        String mime = activity.getContentResolver().getType(u);
        android.database.Cursor c = null;
        try {
            c = activity.getContentResolver().query(u, new String[]{android.provider.OpenableColumns.DISPLAY_NAME}, null, null, null);
            if (c != null && c.moveToFirst()) name = c.getString(0);
        } catch (Exception ignored) {} finally { if (c != null) c.close(); }
        if (mime == null) mime = "*/*";
        return new String[]{name, mime};
    }

    private long sizeOf(Uri u) {
        android.database.Cursor c = null;
        try {
            c = activity.getContentResolver().query(u, new String[]{android.provider.OpenableColumns.SIZE}, null, null, null);
            if (c != null && c.moveToFirst()) return Math.max(0, c.getLong(0));
        } catch (Exception ignored) {} finally { if (c != null) c.close(); }
        return 0;
    }

    private String readSmallText(Uri u, String name, String mime) {
        String n = name.toLowerCase(java.util.Locale.ROOT);
        boolean text = mime.startsWith("text/") || n.endsWith(".md") || n.endsWith(".py") || n.endsWith(".html") ||
                n.endsWith(".htm") || n.endsWith(".js") || n.endsWith(".ts") || n.endsWith(".css") ||
                n.endsWith(".json") || n.endsWith(".xml") || n.endsWith(".csv") || n.endsWith(".txt") ||
                n.endsWith(".yaml") || n.endsWith(".yml") || n.endsWith(".java") || n.endsWith(".kt") ||
                n.endsWith(".gradle") || n.endsWith(".toml") || n.endsWith(".sql") || n.endsWith(".sh");
        if (!text) return "";
        try (InputStream in = activity.getContentResolver().openInputStream(u);
             ByteArrayOutputStream out = new ByteArrayOutputStream()) {
            if (in == null) return "";
            byte[] b = new byte[8192]; int total=0, r;
            while ((r=in.read(b))>0 && total<120000) { int take=Math.min(r,120000-total); out.write(b,0,take); total+=take; if(take<r) break; }
            return out.toString("UTF-8");
        } catch (Exception e) { return ""; }
    }
}
