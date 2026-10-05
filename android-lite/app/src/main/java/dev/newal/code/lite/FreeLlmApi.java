package dev.newal.code.lite;

import android.content.Context;

import org.json.JSONObject;

import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.net.HttpURLConnection;
import java.net.URL;

/**
 * Local FreeLLMAPI supervisor for the phone. The router itself runs in Termux
 * on 127.0.0.1:3001; no Wi-Fi link or second device is involved.
 */
final class FreeLlmApi {
    private static final String PING = "http://127.0.0.1:3001/api/ping";
    private static final String DASHBOARD = "http://127.0.0.1:3001/";
    private static final String HOME = "$HOME/.musabai/freellmapi";
    private static final String REPO = "https://github.com/CP102-BOT/freellmapi.git";

    private FreeLlmApi() {}

    static JSONObject handle(Context ctx, JSONObject a) throws Exception {
        String action = a.optString("action", "");
        if ("freellmapi_status".equals(action)) {
            return status(ctx);
        }
        if ("freellmapi_setup".equals(action)) {
            requireTermux(ctx);
            Termux.run(ctx, setupCommand(false));
            return ok().put("launched", true).put("message", "FreeLLMAPI setup started in Termux");
        }
        if ("freellmapi_update".equals(action)) {
            requireTermux(ctx);
            Termux.run(ctx, setupCommand(true));
            return ok().put("launched", true).put("message", "FreeLLMAPI update started in Termux");
        }
        if ("freellmapi_start".equals(action)) {
            requireTermux(ctx);
            Termux.run(ctx, startCommand());
            return ok().put("launched", true).put("message", "FreeLLMAPI start requested");
        }
        if ("freellmapi_stop".equals(action)) {
            requireTermux(ctx);
            Termux.run(ctx, "pkill -f 'server/dist/index.js' >/dev/null 2>&1 || true");
            return ok().put("launched", true).put("message", "FreeLLMAPI stop requested");
        }
        throw new IllegalArgumentException("Unknown FreeLLMAPI action");
    }

    private static JSONObject status(Context ctx) throws Exception {
        boolean installed = Termux.installed(ctx);
        boolean allowed = installed && Termux.allowed(ctx);
        boolean up = ping();
        return ok()
                .put("termux_installed", installed)
                .put("termux_allowed", allowed)
                .put("up", up)
                .put("endpoint", "http://127.0.0.1:3001/v1")
                .put("dashboard", DASHBOARD);
    }

    private static void requireTermux(Context ctx) {
        if (!Termux.installed(ctx)) {
            throw new IllegalStateException("Termux is not installed");
        }
        if (!Termux.allowed(ctx)) {
            throw new IllegalStateException("Termux RUN_COMMAND permission is required");
        }
    }

    private static boolean ping() {
        HttpURLConnection c = null;
        try {
            c = (HttpURLConnection) new URL(PING).openConnection();
            c.setConnectTimeout(800);
            c.setReadTimeout(1200);
            c.setRequestMethod("GET");
            if (c.getResponseCode() != 200) return false;
            try (BufferedReader r = new BufferedReader(new InputStreamReader(c.getInputStream()))) {
                String text = r.readLine();
                return text != null && text.contains(""status":"ok"");
            }
        } catch (Exception ignored) {
            return false;
        } finally {
            if (c != null) c.disconnect();
        }
    }

    private static String setupCommand(boolean update) {
        String install =
                "set -e; " +
                "pkg install -y git nodejs-lts python clang make pkg-config openssl >/dev/null; " +
                "mkdir -p $HOME/.musabai; ";
        String source = update
                ? "if [ -d " + HOME + "/.git ]; then git -C " + HOME + " fetch --depth 1 origin master && git -C " + HOME + " reset --hard origin/master; " +
                  "else git clone --depth 1 " + REPO + " " + HOME + "; fi; "
                : "if [ ! -d " + HOME + "/.git ]; then git clone --depth 1 " + REPO + " " + HOME + "; fi; ";
        String build =
                "cd " + HOME + "; " +
                "if [ ! -f .env ]; then umask 077; printf 'ENCRYPTION_KEY=%s\\nPORT=3001\\nHOST=127.0.0.1\\n' "$(openssl rand -hex 32)" > .env; fi; " +
                "npm ci; npm run build; " +
                "pkill -f 'server/dist/index.js' >/dev/null 2>&1 || true; " +
                "nohup env NODE_ENV=production HOST=127.0.0.1 PORT=3001 node server/dist/index.js > $HOME/.musabai/freellmapi.log 2>&1 < /dev/null &";
        return install + source + build;
    }

    private static String startCommand() {
        return "set -e; cd " + HOME + "; " +
                "pkill -f 'server/dist/index.js' >/dev/null 2>&1 || true; " +
                "nohup env NODE_ENV=production HOST=127.0.0.1 PORT=3001 node server/dist/index.js > $HOME/.musabai/freellmapi.log 2>&1 < /dev/null &";
    }

    private static JSONObject ok() throws Exception {
        return new JSONObject().put("ok", true);
    }
}
