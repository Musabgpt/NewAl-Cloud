package com.musab.newalcloud;

import android.content.Context;
import android.content.SharedPreferences;
import android.webkit.JavascriptInterface;
import android.webkit.WebView;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.util.UUID;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/**
 * Action #43 transport bridge.
 *
 * When Termux/NewAl is linked, every Action #43 API call is proxied to the
 * real NewAl Python agent running in Termux. That preserves the original
 * sessions, tools, terminal, Git, GitHub, plugins, skills, MCP, review,
 * approvals and verification loop. The model configured in that agent is
 * NewAl-Cloud's keyless kilo-auto/free heart.
 *
 * Before Termux is linked, the bridge falls back to the native cloud chat.
 */
public final class WebBridge {
    private static final String TERMUX_BASE = "http://127.0.0.1:8791";
    private final MainActivity activity;
    private final SharedPreferences prefs;
    private final RemoteChat chat = new RemoteChat();
    private final ExecutorService pool = Executors.newSingleThreadExecutor();
    private volatile boolean eventsStarted;

    WebBridge(MainActivity activity, WebView web) {
        this.activity = activity;
        this.prefs = activity.getSharedPreferences("newal_cloud", Context.MODE_PRIVATE);
    }

    @JavascriptInterface
    public String api(String path, String body, String method) {
        try {
            String p = path == null ? "" : path;
            String b = body == null || body.isEmpty() ? "{}" : body;
            String m = method == null ? "GET" : method.toUpperCase();

            // The real Action #43 server becomes the primary engine as soon as
            // Termux is linked. This is what enables the complete agent loop.
            if (!p.equals("/api/termux/link") && termuxUp()) {
                startTermuxEvents();
                String proxied = proxy(p, b, m);
                if (proxied != null) return proxied;
            }

            if (p.equals("/api/termux/link")) return termuxLink();
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
            if (p.equals("/api/cloud")) return "[]";
            if (p.startsWith("/api/cloud/")) return "{}";
            if (p.startsWith("/api/browse")) return browse();
            if (p.equals("/api/mkdir")) return new JSONObject().put("path", "Cloud").toString();
            if (p.equals("/api/doctor")) return "{\"ok\":true,\"message\":\"NewAl-Cloud remote engine ready. Link Termux for the full Action #43 agent.\"}";
            if (p.equals("/api/speedtest")) return "{\"ok\":true}";
            if (p.startsWith("/api/files")) return "[]";
            if (p.startsWith("/api/extensions")) return "{\"agents\":[],\"skills\":[],\"commands\":[],\"instructions\":[],\"plugins\":[],\"marketplaces\":[],\"hooks\":{},\"mcp\":[]}";
            if (p.equals("/api/plugins")) return "{}";
            if (p.equals("/api/github")) return "{\"connected\":false}";
            if (p.startsWith("/api/github/")) return "{\"error\":\"Link Termux to enable Action #43 GitHub operations.\"}";
            if (p.equals("/api/clipboard")) return "{}";
            return "{}";
        } catch (Exception e) {
            try { return new JSONObject().put("error", e.getMessage() == null ? "Cloud bridge error" : e.getMessage()).toString(); }
            catch (Exception ignored) { return "{\"error\":\"Cloud bridge error\"}"; }
        }
    }

    private String termuxKey() {
        String k = prefs.getString("termux_key", "");
        if (k.isEmpty()) {
            k = UUID.randomUUID().toString().replace("-", "") + UUID.randomUUID().toString().replace("-", "");
            prefs.edit().putString("termux_key", k).apply();
        }
        return k;
    }

    private String termuxLink() throws Exception {
        String key = termuxKey();
        String zip = "https://github.com/Musabgpt/NewAl/archive/refs/heads/ccr-e40af0a0-eec37q.zip";
        String command =
                "pkg install -y python curl unzip >/dev/null 2>&1 && " +
                "H=\$HOME/.newal-cloud && rm -rf \$H && mkdir -p \$H/config && " +
                "curl -L --fail --retry 5 '" + zip + "' -o \$H/newal.zip && " +
                "python -c \"import zipfile,sys; zipfile.ZipFile(sys.argv[1]).extractall(sys.argv[2])\" \$H/newal.zip \$H && " +
                "mv \$H/NewAl-ccr-e40af0a0-eec37q \$H/src && rm -f \$H/newal.zip && " +
                "printf '%s' '" + key + "' > \$H/key && chmod 600 \$H/key && " +
                "PYTHONPATH=\$H/src/desktop NEWAL_CODE_HOME=\$H/config python -c \"from newal_code import settings; settings.save({'model':'kilo-auto/free','models':{'kilo-auto/free':{'provider':'openai','base_url':'https://api.kilo.ai/api/gateway/v1','model':'kilo-auto/free','api_key':'','name':'FreeLLMAPI • Auto Free','context':256000}},'mode':'auto-edit','verify':True,'test_after_edit':True,'auto_context':True,'web':True})\" && " +
                "printf '#!/data/data/com.termux/files/usr/bin/bash\\nH=\$HOME/.newal-cloud\\nexport PYTHONPATH=\$H/src/desktop NEWAL_CODE_HOME=\$H/config NEWAL_SERVER_KEY=\$(cat \$H/key)\\nexec python -m newal_code \"\$@\"\\n' > \$PREFIX/bin/newal && chmod 700 \$PREFIX/bin/newal && " +
                "pkill -f 'newal_code app --port 8791' >/dev/null 2>&1 || true; " +
                "cd \$HOME && nohup env PYTHONPATH=\$H/src/desktop NEWAL_CODE_HOME=\$H/config NEWAL_SERVER_KEY=\$(cat \$H/key) python -m newal_code app --port 8791 --no-browser >\$H/server.log 2>&1 & " +
                "echo 'NewAl Cloud linked: full Action #43 engine is starting on port 8791.'";
        return new JSONObject().put("command", command).put("key", key).put("port", 8791).toString();
    }

    private boolean termuxUp() {
        try {
            URL u = new URL(TERMUX_BASE + "/icon.svg");
            HttpURLConnection c = (HttpURLConnection) u.openConnection();
            c.setConnectTimeout(350);
            c.setReadTimeout(500);
            c.setRequestProperty("X-NewAl-Key", prefs.getString("termux_key", ""));
            int code = c.getResponseCode();
            c.disconnect();
            return code >= 200 && code < 500;
        } catch (Exception e) {
            return false;
        }
    }

    private String proxy(String path, String body, String method) {
        HttpURLConnection c = null;
        try {
            String sep = path.contains("?") ? "&" : "?";
            URL u = new URL(TERMUX_BASE + path);
            c = (HttpURLConnection) u.openConnection();
            c.setConnectTimeout(2500);
            c.setReadTimeout(120000);
            c.setRequestMethod(method);
            c.setRequestProperty("X-NewAl-Key", prefs.getString("termux_key", ""));
            c.setRequestProperty("Accept", "application/json");
            if (!"GET".equals(method)) {
                c.setDoOutput(true);
                c.setRequestProperty("Content-Type", "application/json; charset=utf-8");
                byte[] data = body.getBytes(StandardCharsets.UTF_8);
                try (OutputStream o = c.getOutputStream()) { o.write(data); }
            }
            int code = c.getResponseCode();
            BufferedReader br = new BufferedReader(new InputStreamReader(
                    code >= 400 ? c.getErrorStream() : c.getInputStream(), StandardCharsets.UTF_8));
            StringBuilder out = new StringBuilder();
            for (String line; (line = br.readLine()) != null; ) out.append(line);
            if (code >= 400) {
                try { return new JSONObject().put("error", out.toString()).toString(); }
                catch (Exception ignored) { return "{\"error\":\"Termux engine error\"}"; }
            }
            return out.toString();
        } catch (Exception e) {
            return null;
        } finally {
            if (c != null) c.disconnect();
        }
    }

    private synchronized void startTermuxEvents() {
        if (eventsStarted) return;
        eventsStarted = true;
        pool.execute(() -> {
            while (true) {
                HttpURLConnection c = null;
                try {
                    URL u = new URL(TERMUX_BASE + "/api/events");
                    c = (HttpURLConnection) u.openConnection();
                    c.setConnectTimeout(2500);
                    c.setReadTimeout(0);
                    c.setRequestProperty("X-NewAl-Key", prefs.getString("termux_key", ""));
                    try (BufferedReader br = new BufferedReader(new InputStreamReader(c.getInputStream(), StandardCharsets.UTF_8))) {
                        for (String line; (line = br.readLine()) != null; ) {
                            if (!line.startsWith("data:")) continue;
                            String raw = line.substring(5).trim();
                            if (!raw.isEmpty()) {
                                try { emit(new JSONObject(raw)); } catch (Exception ignored) {}
                            }
                        }
                    }
                } catch (Exception ignored) {
                    try { Thread.sleep(1200); } catch (InterruptedException e) { return; }
                } finally {
                    if (c != null) c.disconnect();
                }
            }
        });
    }

    private String state() throws Exception {
        JSONObject settings = new JSONObject();
        settings.put("lang", "ar");
        settings.put("theme", "system");
        settings.put("model", Providers.MODEL);
        settings.put("mode", "auto-edit");
        settings.put("reasoning", "auto");
        settings.put("verify", true);
        settings.put("test_after_edit", true);
        settings.put("auto_context", true);
        settings.put("web", true);
        settings.put("onboarded", true);
        settings.put("env", "local");
        JSONObject hw = new JSONObject();
        hw.put("cores", Runtime.getRuntime().availableProcessors());
        hw.put("ram_gb", 0);
        hw.put("tier", "cloud");
        return new JSONObject().put("settings", settings).put("hardware", hw)
                .put("projects", new JSONArray().put("Cloud")).put("sandbox", false)
                .put("busy", new JSONArray()).toString();
    }

    private String models() throws Exception {
        return new JSONObject().put("recommended", Providers.MODEL)
                .put("models", new JSONArray().put(new JSONObject().put("id", Providers.MODEL)
                        .put("name", "FreeLLMAPI • Auto Free").put("provider", "kilo").put("downloaded", true)))
                .put("discovered", new JSONArray()).toString();
    }

    private String providers() throws Exception {
        return new JSONObject().put("providers", new JSONArray().put(new JSONObject()
                .put("id", "kilo").put("name", Providers.NAME).put("connected", true).put("keyless", true))).toString();
    }

    private String settings(JSONObject patch) throws Exception { return state(); }

    private String system(JSONObject ignored) throws Exception {
        return new JSONObject().put("access", "cloud").put("internet", true).put("llama", false)
                .put("termux", termuxUp()).put("message", termuxUp()
                        ? "Full Action #43 engine is running in Termux; cloud heart: kilo-auto/free."
                        : "Cloud chat engine active. Link Termux for the full Action #43 agent.")
                .toString();
    }

    private String browse() throws Exception {
        return new JSONObject().put("path", "Cloud").put("dirs", new JSONArray()).put("files", new JSONArray()).toString();
    }

    private String createSession(JSONObject req) throws Exception {
        String id = UUID.randomUUID().toString();
        JSONObject meta = new JSONObject().put("id", id).put("root", req.optString("root", "Cloud"))
                .put("origin", req.optString("root", "Cloud")).put("title", "New thread")
                .put("model", Providers.MODEL).put("mode", req.optString("mode", "auto-edit"))
                .put("reasoning", "auto").put("worktree", false);
        JSONObject rec = new JSONObject().put("id", id).put("meta", meta)
                .put("events", new JSONArray()).put("messages", new JSONArray());
        saveSession(rec);
        return new JSONObject().put("id", id).put("meta", meta).toString();
    }

    private String session(String id) throws Exception {
        JSONObject rec = findSession(id);
        if (rec == null) return new JSONObject().put("error", "Session not found").toString();
        return new JSONObject().put("meta", rec.getJSONObject("meta")).put("events", rec.getJSONArray("events"))
                .put("busy", false).put("approvals", new JSONArray()).put("changes", new JSONArray()).toString();
    }

    private String sessionSettings(String id, JSONObject patch) throws Exception {
        JSONObject rec = findSession(id);
        if (rec == null) return new JSONObject().put("error", "Session not found").toString();
        JSONObject meta = rec.getJSONObject("meta");
        if (patch.has("mode")) meta.put("mode", patch.get("mode"));
        if (patch.has("reasoning")) meta.put("reasoning", patch.get("reasoning"));
        saveSession(rec);
        return new JSONObject().put("meta", meta).toString();
    }

    private String sessions() throws Exception {
        JSONArray all = loadSessions(), out = new JSONArray();
        for (int i = 0; i < all.length(); i++) {
            JSONObject rec = all.getJSONObject(i), meta = rec.getJSONObject("meta");
            out.put(new JSONObject().put("id", rec.getString("id"))
                    .put("title", meta.optString("title", "New thread"))
                    .put("root", meta.optString("root", "Cloud")).put("origin", meta.optString("origin", "Cloud"))
                    .put("updated", System.currentTimeMillis() / 1000.0));
        }
        return out.toString();
    }

    private String startSend(String path, JSONObject req) throws Exception {
        final String sid = getId(path);
        JSONObject rec = findSession(sid);
        if (rec == null) throw new IllegalStateException("Session not found");
        final String text = req.optString("text", "").trim();
        if (text.isEmpty()) return "{}";
        JSONArray old = rec.getJSONArray("messages");
        java.util.List<RemoteChat.Msg> msgs = new java.util.ArrayList<>();
        for (int i = 0; i < old.length(); i++) {
            JSONObject x = old.getJSONObject(i);
            msgs.add(new RemoteChat.Msg(x.getString("role"), x.getString("content")));
        }
        old.put(new JSONObject().put("role", "user").put("content", text));
        saveSession(rec);
        JSONObject start = new JSONObject().put("type", "turn_start").put("session", sid)
                .put("text", text).put("t", System.currentTimeMillis() / 1000.0);
        emit(start);
        pool.execute(() -> {
            StringBuilder answer = new StringBuilder();
            try {
                msgs.add(new RemoteChat.Msg("user", text));
                chat.chat(Providers.ENDPOINT, "", Providers.MODEL, msgs, 4096, 0.2, delta -> {
                    answer.append(delta);
                    try { emit(new JSONObject().put("type", "text_delta").put("session", sid).put("text", delta)); }
                    catch (Exception ignored) {}
                });
                JSONObject now = findSession(sid);
                if (now != null) {
                    now.getJSONArray("messages").put(new JSONObject().put("role", "assistant").put("content", answer.toString()));
                    emit(new JSONObject().put("type", "turn_end").put("session", sid).put("seconds", 0).put("steps", 1)
                            .put("answer", answer.toString()));
                    saveSession(now);
                }
            } catch (Exception e) {
                try { emit(new JSONObject().put("type", "turn_end").put("session", sid)
                        .put("error", e.getMessage() == null ? "Cloud request failed" : e.getMessage())); } catch (Exception ignored) {}
            }
        });
        return new JSONObject().put("started", true).toString();
    }

    private void emit(JSONObject ev) {
        activity.js("window.__newalCloudEvent&&window.__newalCloudEvent(" + JSONObject.quote(ev.toString()) + ")");
    }

    private static String getId(String path) {
        String p = path; int q = p.indexOf('?'); if (q >= 0) p = p.substring(0, q);
        String[] parts = p.split("/"); return parts.length > 3 ? parts[3] : "";
    }

    private JSONArray loadSessions() throws Exception { return new JSONArray(prefs.getString("sessions", "[]")); }

    private JSONObject findSession(String id) throws Exception {
        JSONArray all = loadSessions();
        for (int i = 0; i < all.length(); i++) if (id.equals(all.getJSONObject(i).optString("id"))) return all.getJSONObject(i);
        return null;
    }

    private synchronized void saveSession(JSONObject rec) throws Exception {
        JSONArray all = loadSessions(); boolean replaced = false;
        for (int i = 0; i < all.length(); i++) if (rec.optString("id").equals(all.getJSONObject(i).optString("id"))) {
            all.put(i, rec); replaced = true; break;
        }
        if (!replaced) all.put(rec);
        prefs.edit().putString("sessions", all.toString()).apply();
    }

    @JavascriptInterface public void stop() { chat.cancel(); }
}