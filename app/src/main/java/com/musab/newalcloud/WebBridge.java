package com.musab.newalcloud;

import android.content.Context;
import android.content.SharedPreferences;
import android.webkit.JavascriptInterface;
import android.webkit.WebView;

import org.json.JSONArray;
import org.json.JSONObject;

import java.util.ArrayList;
import java.util.List;
import java.util.UUID;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/**
 * Compatibility layer for the Action #43 UI.
 * The UI remains the original NewAl Code UI; only its /api transport is
 * redirected to the NewAl-Cloud engine and the keyless FreeLLMAPI route.
 */
public final class WebBridge {
    private final MainActivity activity;
    private final WebView web;
    private final RemoteChat chat = new RemoteChat();
    private final ExecutorService pool = Executors.newSingleThreadExecutor();
    private final SharedPreferences prefs;

    WebBridge(MainActivity activity, WebView web) {
        this.activity = activity;
        this.web = web;
        this.prefs = activity.getSharedPreferences("newal_cloud", Context.MODE_PRIVATE);
    }

    @JavascriptInterface
    public String api(String path, String body, String method) {
        try {
            String p = path == null ? "" : path;
            String b = body == null || body.isEmpty() ? "{}" : body;
            String m = method == null ? "GET" : method.toUpperCase();

            if (p.equals("/api/state")) return state();
            if (p.equals("/api/sessions") && "GET".equals(m)) return sessions();
            if (p.equals("/api/sessions") && "POST".equals(m)) return createSession(new JSONObject(b));
            if (p.matches("/api/sessions/[^/]+/send")) return startSend(p, new JSONObject(b));
            if (p.matches("/api/sessions/[^/]+$")) return session(getId(p));
            if (p.matches("/api/sessions/[^/]+/settings")) return sessionSettings(getId(p), new JSONObject(b));
            if (p.matches("/api/sessions/[^/]+/interrupt")) { chat.cancel(); return "{}"; }
            if (p.matches("/api/sessions/[^/]+/changes")) return "{\"git\":null,\"changes\":[]}";
            if (p.equals("/api/sessions/delete")) return "{}";
            if (p.equals("/api/models")) return models();
            if (p.equals("/api/commands") || p.startsWith("/api/commands?")) return "[]";
            if (p.equals("/api/git") || p.startsWith("/api/git?")) return "{\"git\":false}";
            if (p.equals("/api/providers")) return providers();
            if (p.equals("/api/settings") && "POST".equals(m)) return settings(new JSONObject(b));
            if (p.equals("/api/settings")) return settings(new JSONObject());
            if (p.equals("/api/system")) return system(new JSONObject(b));
            if (p.equals("/api/system") && "GET".equals(m)) return system(new JSONObject());
            if (p.equals("/api/cloud") && "POST".equals(m)) return "{\"error\":\"Cloud tasks are already the native NewAl-Cloud chat engine.\"}";
            if (p.equals("/api/cloud")) return "[]";
            if (p.startsWith("/api/cloud/")) return "{}";
            if (p.startsWith("/api/browse")) return browse();
            if (p.equals("/api/mkdir")) return new JSONObject().put("path", "Cloud").toString();
            if (p.equals("/api/doctor")) return "{\"ok\":true,\"message\":\"NewAl-Cloud remote engine ready.\"}";
            if (p.equals("/api/speedtest")) return "{\"ok\":true}";
            if (p.startsWith("/api/files")) return "[]";
            if (p.startsWith("/api/extensions")) return "{\"extensions\":[]}";
            if (p.equals("/api/plugins")) return "{}";
            if (p.equals("/api/github")) return "{\"connected\":false}";
            if (p.startsWith("/api/github/")) return "{\"error\":\"GitHub project actions are not enabled in Cloud chat mode.\"}";
            if (p.startsWith("/api/termux/")) return "{\"error\":\"Termux is not required by Cloud chat mode.\"}";
            if (p.equals("/api/clipboard")) return "{}";
            return "{}";
        } catch (Exception e) {
            try { return new JSONObject().put("error", e.getMessage() == null ? "Cloud bridge error" : e.getMessage()).toString(); }
            catch (Exception ignored) { return "{\"error\":\"Cloud bridge error\"}"; }
        }
    }

    private String state() throws Exception {
        JSONObject settings = new JSONObject();
        settings.put("lang", "ar");
        settings.put("theme", "system");
        settings.put("model", Providers.MODEL);
        settings.put("mode", "auto-edit");
        settings.put("reasoning", "auto");
        settings.put("onboarded", true);
        settings.put("env", "local");

        JSONObject hw = new JSONObject();
        hw.put("cores", Runtime.getRuntime().availableProcessors());
        hw.put("ram_gb", 0);
        hw.put("tier", "cloud");

        JSONObject out = new JSONObject();
        out.put("settings", settings);
        out.put("hardware", hw);
        out.put("projects", new JSONArray().put("Cloud"));
        out.put("sandbox", false);
        out.put("busy", new JSONArray());
        return out.toString();
    }

    private String models() throws Exception {
        JSONObject out = new JSONObject();
        out.put("recommended", Providers.MODEL);
        JSONArray ms = new JSONArray();
        ms.put(new JSONObject()
                .put("id", Providers.MODEL)
                .put("name", "FreeLLMAPI • Auto Free")
                .put("provider", "kilo")
                .put("downloaded", true));
        out.put("models", ms);
        out.put("discovered", new JSONArray());
        return out.toString();
    }

    private String providers() throws Exception {
        return new JSONObject()
                .put("providers", new JSONArray().put(new JSONObject()
                        .put("id", "kilo")
                        .put("name", Providers.NAME)
                        .put("connected", true)
                        .put("keyless", true)))
                .toString();
    }

    private String settings(JSONObject patch) throws Exception {
        // Cloud mode intentionally has no API-key setting.
        return state();
    }

    private String system(JSONObject ignored) throws Exception {
        return new JSONObject()
                .put("access", "cloud")
                .put("internet", true)
                .put("llama", false)
                .put("termux", false)
                .put("message", "Cloud engine active; no local GGUF is used.")
                .toString();
    }

    private String browse() throws Exception {
        JSONObject d = new JSONObject();
        d.put("path", "Cloud");
        d.put("dirs", new JSONArray());
        d.put("files", new JSONArray());
        return d.toString();
    }

    private String createSession(JSONObject req) throws Exception {
        String id = UUID.randomUUID().toString();
        JSONObject meta = new JSONObject();
        meta.put("id", id);
        meta.put("root", req.optString("root", "Cloud"));
        meta.put("origin", req.optString("root", "Cloud"));
        meta.put("title", "New thread");
        meta.put("model", Providers.MODEL);
        meta.put("mode", req.optString("mode", "auto-edit"));
        meta.put("reasoning", "auto");
        meta.put("worktree", false);

        JSONObject rec = new JSONObject();
        rec.put("id", id);
        rec.put("meta", meta);
        rec.put("events", new JSONArray());
        rec.put("messages", new JSONArray());
        saveSession(rec);

        return new JSONObject().put("id", id).put("meta", meta).toString();
    }

    private String session(String id) throws Exception {
        JSONObject rec = findSession(id);
        if (rec == null) return new JSONObject().put("error", "Session not found").toString();
        JSONObject out = new JSONObject();
        out.put("meta", rec.getJSONObject("meta"));
        out.put("events", rec.getJSONArray("events"));
        out.put("busy", false);
        out.put("approvals", new JSONArray());
        out.put("changes", new JSONArray());
        return out.toString();
    }

    private String sessionSettings(String id, JSONObject patch) throws Exception {
        JSONObject rec = findSession(id);
        if (rec == null) return new JSONObject().put("error", "Session not found").toString();
        JSONObject meta = rec.getJSONObject("meta");
        if (patch.has("mode")) meta.put("mode", patch.get("mode"));
        if (patch.has("reasoning")) meta.put("reasoning", patch.get("reasoning"));
        if (patch.has("model")) meta.put("model", Providers.MODEL);
        saveSession(rec);
        return new JSONObject().put("meta", meta).toString();
    }

    private String sessions() throws Exception {
        JSONArray all = loadSessions();
        JSONArray out = new JSONArray();
        for (int i = 0; i < all.length(); i++) {
            JSONObject rec = all.getJSONObject(i);
            JSONObject meta = rec.getJSONObject("meta");
            out.put(new JSONObject()
                    .put("id", rec.getString("id"))
                    .put("title", meta.optString("title", "New thread"))
                    .put("root", meta.optString("root", "Cloud"))
                    .put("origin", meta.optString("origin", "Cloud"))
                    .put("updated", System.currentTimeMillis() / 1000.0));
        }
        return out.toString();
    }

    private String startSend(String path, JSONObject req) throws Exception {
        final String sid = getId(path);
        JSONObject rec = findSession(sid);
        if (rec == null) throw new IllegalStateException("Session not found");

        final String text = req.optString("text", "").trim();
        final String lang = req.optString("lang", "ar");
        if (text.isEmpty()) return "{}";

        JSONArray oldMessages = rec.getJSONArray("messages");
        final List<RemoteChat.Msg> history = new ArrayList<>();
        for (int i = 0; i < oldMessages.length(); i++) {
            JSONObject x = oldMessages.getJSONObject(i);
            history.add(new RemoteChat.Msg(x.getString("role"), x.getString("content")));
        }

        JSONObject start = new JSONObject();
        start.put("type", "turn_start");
        start.put("session", sid);
        start.put("text", text);
        start.put("t", System.currentTimeMillis() / 1000.0);
        appendEvent(rec, start);
        JSONObject user = new JSONObject().put("role", "user").put("content", text);
        oldMessages.put(user);
        saveSession(rec);
        emit(start);

        pool.execute(() -> {
            StringBuilder answer = new StringBuilder();
            try {
                List<RemoteChat.Msg> msgs = new ArrayList<>(history);
                msgs.add(new RemoteChat.Msg("user", text));
                chat.chat(Providers.ENDPOINT, "", Providers.MODEL, msgs, 2048, 0.7, delta -> {
                    answer.append(delta);
                    try {
                        JSONObject ev = new JSONObject()
                                .put("type", "text_delta")
                                .put("session", sid)
                                .put("text", delta);
                        appendEvent(findSession(sid), ev);
                        emit(ev);
                    } catch (Exception ignored) {}
                });

                JSONObject now = findSession(sid);
                if (now != null) {
                    now.getJSONArray("messages").put(new JSONObject().put("role", "assistant").put("content", answer.toString()));
                    JSONObject meta = now.getJSONObject("meta");
                    if ("New thread".equals(meta.optString("title"))) {
                        String title = text.length() > 42 ? text.substring(0, 42) + "…" : text;
                        meta.put("title", title);
                    }
                    JSONObject done = new JSONObject()
                            .put("type", "turn_end")
                            .put("session", sid)
                            .put("seconds", 0)
                            .put("steps", 1)
                            .put("answer", answer.toString());
                    appendEvent(now, done);
                    saveSession(now);
                    emit(done);
                }
            } catch (Exception e) {
                try {
                    JSONObject ev = new JSONObject().put("type", "turn_end").put("session", sid)
                            .put("error", e.getMessage() == null ? "Cloud request failed" : e.getMessage());
                    JSONObject now = findSession(sid);
                    if (now != null) { appendEvent(now, ev); saveSession(now); }
                    emit(ev);
                } catch (Exception ignored) {}
            }
        });

        return new JSONObject().put("started", true).toString();
    }

    private void emit(JSONObject ev) {
        final String raw = ev.toString();
        activity.js("window.__newalCloudEvent&&window.__newalCloudEvent(" + JSONObject.quote(raw) + ")");
    }

    private static String getId(String path) {
        String p = path;
        int q = p.indexOf('?');
        if (q >= 0) p = p.substring(0, q);
        String[] parts = p.split("/");
        return parts.length > 3 ? parts[3] : "";
    }

    private JSONArray loadSessions() throws Exception {
        String raw = prefs.getString("sessions", "[]");
        return new JSONArray(raw);
    }

    private JSONObject findSession(String id) throws Exception {
        JSONArray all = loadSessions();
        for (int i = 0; i < all.length(); i++) {
            JSONObject x = all.getJSONObject(i);
            if (id.equals(x.optString("id"))) return x;
        }
        return null;
    }

    private synchronized void saveSession(JSONObject rec) throws Exception {
        JSONArray all = loadSessions();
        boolean replaced = false;
        for (int i = 0; i < all.length(); i++) {
            if (rec.optString("id").equals(all.getJSONObject(i).optString("id"))) {
                all.put(i, rec);
                replaced = true;
                break;
            }
        }
        if (!replaced) all.put(rec);
        prefs.edit().putString("sessions", all.toString()).apply();
    }

    private synchronized void appendEvent(JSONObject rec, JSONObject ev) throws Exception {
        if (rec != null) rec.getJSONArray("events").put(ev);
    }

    @JavascriptInterface
    public void stop() {
        chat.cancel();
    }
}
