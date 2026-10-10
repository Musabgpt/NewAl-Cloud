package com.musab.newalcloud;

import org.json.JSONArray;
import org.json.JSONException;
import org.json.JSONObject;

import java.io.BufferedReader;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.util.List;

/** Streaming client for OpenAI-compatible /chat/completions endpoints (SSE). */
final class RemoteChat {
    interface Listener { void onText(String delta); }

    static final class Msg {
        final String role, text;
        Msg(String role, String text) { this.role = role; this.text = text; }
    }

    static final class Result {
        String text = "";
        long firstTokenMs = -1, totalMs;
        int chunks;
    }

    static final class ApiException extends IOException {
        private static final long serialVersionUID = 1L;
        final int code;
        final String body, retryAfter;
        ApiException(int code, String body, String retryAfter) {
            super("HTTP " + code);
            this.code = code; this.body = body; this.retryAfter = retryAfter;
        }
    }

    private volatile HttpURLConnection conn;
    private volatile boolean cancelled;

    void cancel() {
        cancelled = true;
        HttpURLConnection c = conn;
        if (c != null) c.disconnect();
    }

    Result chat(String endpoint, String apiKey, String model, List<Msg> messages,
                int maxTokens, double temperature, Listener listener) throws IOException {
        cancelled = false;
        long t0 = System.nanoTime();
        byte[] payload;
        try {
            JSONArray arr = new JSONArray();
            for (Msg m : messages) arr.put(new JSONObject().put("role", m.role).put("content", m.text));
            JSONObject body = new JSONObject()
                    .put("model", model)
                    .put("stream", true)
                    .put("temperature", temperature)
                    .put("max_tokens", maxTokens)
                    .put("messages", arr);
            payload = body.toString().getBytes(StandardCharsets.UTF_8);
        } catch (JSONException e) {
            throw new IOException(e);
        }

        HttpURLConnection c = (HttpURLConnection) new URL(endpoint).openConnection();
        conn = c;
        Result r = new Result();
        StringBuilder sb = new StringBuilder();
        try {
            c.setRequestMethod("POST");
            c.setConnectTimeout(15_000);
            c.setReadTimeout(60_000);
            c.setDoOutput(true);
            c.setRequestProperty("Content-Type", "application/json");
            if (apiKey != null && !apiKey.trim().isEmpty()) {
                c.setRequestProperty("Authorization", "Bearer " + apiKey);
            }
            c.setRequestProperty("Accept", "text/event-stream");
            try (OutputStream o = c.getOutputStream()) { o.write(payload); }

            int code = c.getResponseCode();
            if (code / 100 != 2) {
                throw new ApiException(code, readAll(c.getErrorStream()), c.getHeaderField("Retry-After"));
            }
            try (BufferedReader br = new BufferedReader(new InputStreamReader(c.getInputStream(), StandardCharsets.UTF_8))) {
                String line;
                while (!cancelled && (line = br.readLine()) != null) {
                    if (!line.startsWith("data:")) continue;
                    String data = line.substring(5).trim();
                    if (data.isEmpty()) continue;
                    if (data.equals("[DONE]")) break;
                    String delta = parseDelta(data);
                    if (delta.isEmpty()) continue;
                    if (r.firstTokenMs < 0) r.firstTokenMs = ms(t0);
                    r.chunks++;
                    sb.append(delta);
                    listener.onText(delta);
                }
            }
        } catch (IOException e) {
            // A user-requested stop closes the socket; keep what was already received.
            if (!cancelled) throw e;
        } finally {
            c.disconnect();
            conn = null;
        }
        r.text = sb.toString();
        r.totalMs = ms(t0);
        return r;
    }

    private static String parseDelta(String json) {
        try {
            JSONObject o = new JSONObject(json);
            JSONArray choices = o.optJSONArray("choices");
            if (choices == null || choices.length() == 0) return "";
            JSONObject choice = choices.optJSONObject(0);
            if (choice == null) return "";
            JSONObject delta = choice.optJSONObject("delta");
            if (delta == null || delta.isNull("content")) return "";
            return delta.optString("content", "");
        } catch (JSONException e) {
            return "";
        }
    }

    private static String readAll(InputStream in) {
        if (in == null) return "";
        try (InputStream s = in) {
            ByteArrayOutputStream out = new ByteArrayOutputStream();
            byte[] buf = new byte[4096];
            int n;
            while ((n = s.read(buf)) > 0 && out.size() < 8192) out.write(buf, 0, n);
            return out.toString("UTF-8");
        } catch (IOException e) {
            return "";
        }
    }

    private static long ms(long startNanos) { return (System.nanoTime() - startNanos) / 1_000_000; }
}
