package dev.newal.code.lite;

import android.content.Context;
import org.json.JSONObject;

/** Keystore-backed secret for optional self-hosted research services. */
final class ResearchSecrets {
    private ResearchSecrets() {}

    private static String service(JSONObject a) {
        String name = a.optString("service", "");
        if (!"crawl4ai".equals(name)) throw new IllegalArgumentException("Unknown research service");
        return name;
    }

    private static String record(String service) {
        return "research-service-" + service;
    }

    static JSONObject handle(Context ctx, JSONObject a) throws Exception {
        String action = a.optString("action", "");
        String service = service(a);
        ConnectorVault vault = new ConnectorVault(ctx);
        if ("research_secret_status".equals(action)) {
            JSONObject saved = vault.get(record(service));
            return ok().put("configured", !saved.optString("value", "").isEmpty());
        }
        if ("research_secret_get".equals(action)) {
            JSONObject saved = vault.get(record(service));
            String value = saved.optString("value", "");
            if (value.isEmpty()) throw new IllegalStateException("Research service credential is not configured");
            return ok().put("value", value);
        }
        if ("research_secret_set".equals(action)) {
            String value = a.optString("value", "").trim();
            if (value.length() < 8 || value.length() > 8192 || value.matches(".*\\s+.*"))
                throw new IllegalArgumentException("Invalid research service credential");
            vault.put(record(service), new JSONObject().put("value", value)
                    .put("saved_at", System.currentTimeMillis()));
            return ok().put("configured", true);
        }
        if ("research_secret_remove".equals(action)) {
            vault.remove(record(service));
            return ok().put("configured", false);
        }
        throw new IllegalArgumentException("Unknown research secret operation");
    }

    private static JSONObject ok() throws Exception {
        return new JSONObject().put("ok", true);
    }
}
