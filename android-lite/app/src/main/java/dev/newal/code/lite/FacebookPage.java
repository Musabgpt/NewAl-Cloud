package dev.newal.code.lite;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;
import java.util.Locale;

/**
 * A Facebook Page connected with an access token (Facebook's Graph API): the agent and scheduled tasks post to it
 * without opening the Facebook app, with the screen off and the phone locked. Only Pages: Facebook lets no app post on
 * a person's profile.
 *
 * The token lives only in ConnectorVault (Android Keystore). The interface hands it straight to this class (WebBridge),
 * never through Python; the agent's tools ask for actions (post, the latest posts) and never receive it.
 *
 * Connecting takes a Page token, or a person's token (the Page is then picked from the Pages they manage). With the
 * Meta app's ID and secret, a short-lived person's token is first exchanged for a long-lived one: the Page token it
 * gives does not expire.
 */
final class FacebookPage {
    static final String ID = "facebook";
    static final String NAME = "Facebook Page";
    static final String GRAPH = "https://graph.facebook.com/v26.0";
    static final int MAX_MESSAGE = 60000;
    private static final String RECORD = "facebook";
    private static final int TOKEN_EXPIRED = 190;

    /** Where the Page's record is kept: ConnectorVault on the phone, a map in tests. */
    interface Store {
        JSONObject get(String name) throws Exception;

        void put(String name, JSONObject value) throws Exception;

        void remove(String name) throws Exception;
    }

    /** One Graph API request: method, path after GRAPH, fields (the token among them) -> its JSON answer. */
    interface Graph {
        JSONObject call(String method, String path, String[][] fields) throws Exception;
    }

    /** Facebook's own error: its code (190: the token expired or was revoked) and its message. */
    static final class GraphError extends IllegalStateException {
        final int code;

        GraphError(int code, String message) {
            super(message);
            this.code = code;
        }
    }

    private final Store store;
    private final Graph graph;

    FacebookPage(ConnectorVault vault) {
        this(new Store() {
            @Override public JSONObject get(String name) throws Exception { return vault.get(name); }
            @Override public void put(String name, JSONObject value) throws Exception { vault.put(name, value); }
            @Override public void remove(String name) { vault.remove(name); }
        }, FacebookPage::request);
    }

    FacebookPage(Store store, Graph graph) {
        this.store = store;
        this.graph = graph;
    }

    /** What Connections and the engine see: the Page's name and state, never the token. */
    synchronized JSONObject status() throws Exception {
        JSONObject rec = store.get(RECORD);
        boolean has = rec.has("token");
        return new JSONObject().put("id", ID).put("name", NAME)
                .put("status", has ? rec.optString("status", "connected") : "disconnected")
                .put("account", rec.optString("page_name")).put("configured", true).put("has_credentials", has)
                .put("error", rec.optString("error")).put("tested_at", rec.optLong("tested_at"))
                .put("lasting", rec.optBoolean("lasting")).put("expires_at", rec.optLong("expires_at"))
                .put("transport", "rest")
                .put("generation", rec.optString("page_id")).put("tool_count", has ? 2 : 0);
    }

    synchronized JSONObject connect(String token, String appId, String appSecret, String page) throws Exception {
        token = clean(token);
        if (token.isEmpty()) throw new IllegalArgumentException("Paste the access token");
        boolean lasting = false;
        String warning = "";
        if (!clean(appId).isEmpty() && !clean(appSecret).isEmpty()) {
            try {
                JSONObject longer = graph.call("GET", "/oauth/access_token", new String[][]{
                        {"grant_type", "fb_exchange_token"}, {"client_id", clean(appId)},
                        {"client_secret", clean(appSecret)}, {"fb_exchange_token", token}});
                if (!longer.optString("access_token").isEmpty()) {
                    token = longer.getString("access_token");
                    lasting = true;
                }
            } catch (GraphError e) {
                if (e.code == TOKEN_EXPIRED) throw e;
                warning = "Not made long-lived (" + e.getMessage() + ").";
            }
        }
        JSONObject me;
        try {
            me = graph.call("GET", "/me", new String[][]{{"fields", "id,name,category"}, {"access_token", token}});
        } catch (GraphError e) {
            if (e.code == TOKEN_EXPIRED) throw e;
            me = null;                     // a person's token: a person has no category
        }
        String pageId, pageName, pageToken;
        if (me != null && me.has("category")) {
            pageId = me.getString("id");
            pageName = me.optString("name");
            pageToken = token;
        } else {
            JSONArray pages = graph.call("GET", "/me/accounts", new String[][]{
                    {"fields", "id,name,access_token"}, {"limit", "100"}, {"access_token", token}}).optJSONArray("data");
            if (pages == null || pages.length() == 0) {
                throw new IllegalArgumentException("This token sees no Page: make it with the pages_show_list, "
                        + "pages_read_engagement and pages_manage_posts permissions, and pick your Page");
            }
            JSONObject pick = choose(pages, clean(page));
            pageId = pick.getString("id");
            pageName = pick.optString("name");
            pageToken = pick.getString("access_token");
        }
        JSONObject check = graph.call("GET", "/" + pageId, new String[][]{
                {"fields", "id,name"}, {"access_token", pageToken}});
        // whether the Page token expires (0: never), and whether it may post: Facebook's own answer, when it gives one
        long expires = -1;
        try {
            JSONObject info = graph.call("GET", "/debug_token", new String[][]{
                    {"input_token", pageToken}, {"access_token", token}}).optJSONObject("data");
            if (info != null) {
                expires = info.optLong("expires_at", -1);
                JSONArray scopes = info.optJSONArray("scopes");
                if (scopes != null && !scopes.toString().contains("\"pages_manage_posts\"")) {
                    warning = (warning + " The token lacks pages_manage_posts: posts will fail. Make it again with "
                            + "that permission.").trim();
                }
            }
        } catch (Exception ignored) {
            // unknown: the connection works all the same
        }
        JSONObject rec = new JSONObject().put("token", pageToken).put("page_id", pageId)
                .put("page_name", check.optString("name", pageName)).put("status", "connected")
                .put("lasting", expires == 0 || (expires < 0 && lasting))
                .put("expires_at", Math.max(0, expires)).put("tested_at", System.currentTimeMillis());
        store.put(RECORD, rec);
        return status().put("ok", true).put("warning", warning);
    }

    /** A person who manages several Pages names one (its name or ID); with one Page, that one. */
    static JSONObject choose(JSONArray pages, String want) throws Exception {
        StringBuilder names = new StringBuilder();
        for (int i = 0; i < pages.length(); i++) {
            JSONObject p = pages.getJSONObject(i);
            if (!want.isEmpty() && (want.equals(p.optString("id"))
                    || want.toLowerCase(Locale.ROOT).equals(p.optString("name").toLowerCase(Locale.ROOT)))) {
                return p;
            }
            names.append(i == 0 ? "" : ", ").append(p.optString("name"));
        }
        if (want.isEmpty() && pages.length() == 1) return pages.getJSONObject(0);
        throw new IllegalArgumentException((want.isEmpty() ? "Several Pages" : "No Page named \"" + want + "\"")
                + ": write the Page's name (" + names + ")");
    }

    synchronized JSONObject disconnect() throws Exception {
        store.remove(RECORD);
        return new JSONObject().put("ok", true).put("text", "Disconnected on this phone. Remove the app's access in "
                + "Facebook's settings (Business integrations) to revoke the token itself.");
    }

    synchronized JSONObject test() throws Exception {
        JSONObject rec = connected();
        try {
            JSONObject page = graph.call("GET", "/" + rec.getString("page_id"), new String[][]{
                    {"fields", "id,name"}, {"access_token", rec.getString("token")}});
            rec.put("page_name", page.optString("name", rec.optString("page_name"))).put("status", "connected")
                    .put("error", "").put("tested_at", System.currentTimeMillis());
            store.put(RECORD, rec);
        } catch (GraphError e) {
            remember(rec, e);
            throw e;
        }
        return status().put("ok", true);
    }

    synchronized JSONObject post(String message, String link) throws Exception {
        JSONObject rec = connected();
        message = message == null ? "" : message.trim();
        link = clean(link);
        if (message.isEmpty() && link.isEmpty()) throw new IllegalArgumentException("A post needs text (message)");
        if (message.length() > MAX_MESSAGE) throw new IllegalArgumentException("The post is too long");
        if (!link.isEmpty() && !link.startsWith("https://") && !link.startsWith("http://")) {
            throw new IllegalArgumentException("link: a web address (https://...)");
        }
        String token = rec.getString("token");
        String[][] fields = link.isEmpty()
                ? new String[][]{{"message", message}, {"access_token", token}}
                : message.isEmpty() ? new String[][]{{"link", link}, {"access_token", token}}
                : new String[][]{{"message", message}, {"link", link}, {"access_token", token}};
        JSONObject out;
        try {
            out = graph.call("POST", "/" + rec.getString("page_id") + "/feed", fields);
        } catch (GraphError e) {
            remember(rec, e);
            throw e;
        }
        String id = out.optString("id");
        if (id.isEmpty()) throw new IllegalStateException("Facebook did not return the post");
        String url = "";
        try {
            url = graph.call("GET", "/" + id, new String[][]{{"fields", "permalink_url"}, {"access_token", token}})
                    .optString("permalink_url");
        } catch (Exception ignored) {
            // posted: only its address is missing
        }
        return new JSONObject().put("ok", true).put("data", new JSONObject().put("id", id).put("url", url)
                .put("page", rec.optString("page_name")));
    }

    synchronized JSONObject recent(int limit) throws Exception {
        JSONObject rec = connected();
        int n = Math.max(1, Math.min(limit <= 0 ? 10 : limit, 50));
        JSONObject out;
        try {
            out = graph.call("GET", "/" + rec.getString("page_id") + "/posts", new String[][]{
                    {"fields", "message,created_time,permalink_url"}, {"limit", String.valueOf(n)},
                    {"access_token", rec.getString("token")}});
        } catch (GraphError e) {
            remember(rec, e);
            throw e;
        }
        JSONArray posts = new JSONArray();
        JSONArray data = out.optJSONArray("data");
        for (int i = 0; data != null && i < data.length(); i++) {
            JSONObject p = data.getJSONObject(i);
            posts.put(new JSONObject().put("id", p.optString("id")).put("time", p.optString("created_time"))
                    .put("message", p.optString("message")).put("url", p.optString("permalink_url")));
        }
        return new JSONObject().put("ok", true).put("data", new JSONObject().put("posts", posts)
                .put("page", rec.optString("page_name")));
    }

    private JSONObject connected() throws Exception {
        JSONObject rec = store.get(RECORD);
        if (!rec.has("token")) throw new IllegalStateException("No Facebook Page is connected (Connections > Facebook Page)");
        if ("reauthorize".equals(rec.optString("status"))) {
            throw new IllegalStateException("The Facebook Page's token expired: connect it again (Connections > Facebook Page)");
        }
        return rec;
    }

    /** An expired or revoked token marks the Page for reconnecting (the next calls say so without asking Facebook). */
    private void remember(JSONObject rec, GraphError e) throws Exception {
        if (e.code != TOKEN_EXPIRED) return;
        rec.put("status", "reauthorize").put("error", e.getMessage());
        store.put(RECORD, rec);
    }

    private static String clean(String s) {
        return s == null ? "" : s.trim();
    }

    // ------------------------------------------------------------------ Graph API over HTTPS

    private static JSONObject request(String method, String path, String[][] fields) throws Exception {
        String form = form(fields);
        boolean get = "GET".equals(method);
        HttpURLConnection c = null;
        try {
            c = (HttpURLConnection) new URL(GRAPH + path + (get && !form.isEmpty() ? "?" + form : "")).openConnection();
            c.setRequestMethod(method);
            c.setConnectTimeout(15_000);
            c.setReadTimeout(30_000);
            c.setRequestProperty("Accept", "application/json");
            if (!get) {
                c.setDoOutput(true);
                c.setRequestProperty("Content-Type", "application/x-www-form-urlencoded");
                try (OutputStream out = c.getOutputStream()) {
                    out.write(form.getBytes(StandardCharsets.UTF_8));
                }
            }
            int code = c.getResponseCode();
            InputStream in = code >= 400 ? c.getErrorStream() : c.getInputStream();
            String body = in == null ? "" : new String(read(in), StandardCharsets.UTF_8);
            return answer(code, body);
        } catch (IOException e) {
            // never the address: a GET carries the token in it
            throw new IOException("Facebook could not be reached (" + e.getClass().getSimpleName() + ")");
        } finally {
            if (c != null) c.disconnect();
        }
    }

    /** Facebook's JSON answer, or its error as a GraphError. */
    static JSONObject answer(int code, String body) throws Exception {
        String text = body == null ? "" : body.trim();
        JSONObject json = text.startsWith("{") ? new JSONObject(text) : new JSONObject();
        JSONObject error = json.optJSONObject("error");
        if (code >= 400 || error != null) {
            throw new GraphError(error == null ? code : error.optInt("code", code),
                    error == null ? "Facebook answered HTTP " + code : "Facebook: " + error.optString("message"));
        }
        return json;
    }

    static String form(String[][] fields) throws Exception {
        StringBuilder sb = new StringBuilder();
        for (String[] f : fields) {
            if (sb.length() > 0) sb.append('&');
            sb.append(URLEncoder.encode(f[0], "UTF-8")).append('=').append(URLEncoder.encode(f[1], "UTF-8"));
        }
        return sb.toString();
    }

    private static byte[] read(InputStream in) throws IOException {
        ByteArrayOutputStream out = new ByteArrayOutputStream();
        byte[] b = new byte[8192];
        int n, total = 0;
        while ((n = in.read(b)) > 0) {
            total += n;
            if (total > (1 << 20)) throw new IOException("answer too large");
            out.write(b, 0, n);
        }
        return out.toByteArray();
    }
}
