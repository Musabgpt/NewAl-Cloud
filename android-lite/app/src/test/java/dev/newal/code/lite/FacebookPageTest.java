package dev.newal.code.lite;

import org.json.JSONArray;
import org.json.JSONObject;
import org.junit.Test;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

import static org.junit.Assert.*;

public class FacebookPageTest {
    /** The vault, in memory. */
    static final class Memory implements FacebookPage.Store {
        final Map<String, JSONObject> records = new HashMap<>();

        @Override public JSONObject get(String name) throws Exception {
            JSONObject r = records.get(name);
            return r == null ? new JSONObject() : new JSONObject(r.toString());
        }

        @Override public void put(String name, JSONObject value) throws Exception {
            records.put(name, new JSONObject(value.toString()));
        }

        @Override public void remove(String name) {
            records.remove(name);
        }
    }

    /** Facebook, answering each "METHOD path" from a table; every request is kept. */
    static final class Fake implements FacebookPage.Graph {
        final Map<String, Object> answers = new HashMap<>();
        final List<String> calls = new ArrayList<>();
        final List<Map<String, String>> fields = new ArrayList<>();

        @Override public JSONObject call(String method, String path, String[][] f) throws Exception {
            Map<String, String> m = new HashMap<>();
            for (String[] kv : f) m.put(kv[0], kv[1]);
            calls.add(method + " " + path);
            fields.add(m);
            Object a = answers.get(method + " " + path + " " + m.get("access_token"));
            if (a == null) a = answers.get(method + " " + path);
            if (a instanceof FacebookPage.GraphError) throw (FacebookPage.GraphError) a;
            if (a == null) throw new FacebookPage.GraphError(100, "Facebook: unknown path " + path);
            return new JSONObject(a.toString());
        }
    }

    private static JSONObject page(String id, String name, String token) throws Exception {
        return new JSONObject().put("id", id).put("name", name).put("access_token", token);
    }

    @Test public void aPageTokenConnectsItsPageAndIsNeverShown() throws Exception {
        Memory vault = new Memory();
        Fake fb = new Fake();
        fb.answers.put("GET /me", new JSONObject().put("id", "42").put("name", "My Bakery").put("category", "Bakery"));
        fb.answers.put("GET /42", new JSONObject().put("id", "42").put("name", "My Bakery"));
        JSONObject status = new FacebookPage(vault, fb).connect(" PAGE-TOKEN ", "", "", "");
        assertEquals("connected", status.getString("status"));
        assertEquals("My Bakery", status.getString("account"));
        assertFalse(status.toString().contains("PAGE-TOKEN"));            // what Python and the page see
        assertEquals("PAGE-TOKEN", vault.records.get("facebook").getString("token"));
        assertEquals(List.of("GET /me", "GET /42", "GET /debug_token"), fb.calls);
        assertFalse(status.getBoolean("lasting"));                        // Facebook did not say: not assumed
    }

    @Test public void facebookSaysWhetherTheTokenLastsAndMayPost() throws Exception {
        Fake fb = new Fake();
        fb.answers.put("GET /me", new JSONObject().put("id", "42").put("name", "My Bakery").put("category", "Bakery"));
        fb.answers.put("GET /42", new JSONObject().put("id", "42").put("name", "My Bakery"));
        fb.answers.put("GET /debug_token", new JSONObject().put("data", new JSONObject().put("expires_at", 0)
                .put("scopes", new JSONArray().put("pages_show_list").put("pages_read_engagement"))));
        JSONObject status = new FacebookPage(new Memory(), fb).connect("PT", "", "", "");
        assertTrue(status.getBoolean("lasting"));
        assertTrue(status.getString("warning").contains("pages_manage_posts"));
        fb.answers.put("GET /debug_token", new JSONObject().put("data", new JSONObject().put("expires_at", 1793000000L)
                .put("scopes", new JSONArray().put("pages_manage_posts"))));
        status = new FacebookPage(new Memory(), fb).connect("PT", "", "", "");
        assertFalse(status.getBoolean("lasting"));
        assertEquals(1793000000L, status.getLong("expires_at"));
        assertEquals("", status.getString("warning"));
    }

    @Test public void aFailedExchangeStillConnectsAndSaysSo() throws Exception {
        Fake fb = new Fake();
        fb.answers.put("GET /oauth/access_token", new FacebookPage.GraphError(101, "Facebook: Error validating client secret"));
        fb.answers.put("GET /me", new JSONObject().put("id", "42").put("name", "My Bakery").put("category", "Bakery"));
        fb.answers.put("GET /42", new JSONObject().put("id", "42").put("name", "My Bakery"));
        JSONObject status = new FacebookPage(new Memory(), fb).connect("PT", "id", "wrong", "");
        assertEquals("connected", status.getString("status"));
        assertTrue(status.getString("warning").contains("client secret"));
    }

    @Test public void aPersonsTokenIsMadeLongLivedAndItsPageIsPicked() throws Exception {
        Memory vault = new Memory();
        Fake fb = new Fake();
        fb.answers.put("GET /oauth/access_token", new JSONObject().put("access_token", "LONG-USER"));
        fb.answers.put("GET /me", new FacebookPage.GraphError(100, "Tried accessing nonexisting field (category)"));
        fb.answers.put("GET /me/accounts", new JSONObject().put("data", new JSONArray()
                .put(page("1", "Cafe One", "T1")).put(page("2", "Bakery Two", "T2"))));
        fb.answers.put("GET /2", new JSONObject().put("id", "2").put("name", "Bakery Two"));
        FacebookPage fp = new FacebookPage(vault, fb);
        JSONObject status = fp.connect("SHORT-USER", "app-id", "app-secret", "bakery two");
        assertEquals("Bakery Two", status.getString("account"));
        assertTrue(status.getBoolean("lasting"));
        assertEquals("T2", vault.records.get("facebook").getString("token"));
        assertEquals("SHORT-USER", fb.fields.get(0).get("fb_exchange_token"));
        assertEquals("LONG-USER", fb.fields.get(1).get("access_token"));        // the long-lived token asks for Pages
    }

    @Test public void severalPagesNeedAName() throws Exception {
        Fake fb = new Fake();
        fb.answers.put("GET /me", new FacebookPage.GraphError(100, "no category on a person"));
        fb.answers.put("GET /me/accounts", new JSONObject().put("data", new JSONArray()
                .put(page("1", "Cafe One", "T1")).put(page("2", "Bakery Two", "T2"))));
        try {
            new FacebookPage(new Memory(), fb).connect("USER", "", "", "");
            fail("several Pages and no name");
        } catch (IllegalArgumentException e) {
            assertTrue(e.getMessage().contains("Cafe One, Bakery Two"));
        }
    }

    @Test public void anExpiredTokenIsSaidAtOnce() throws Exception {
        Fake fb = new Fake();
        fb.answers.put("GET /me", new FacebookPage.GraphError(190, "Facebook: Error validating access token"));
        assertThrows(FacebookPage.GraphError.class, () -> new FacebookPage(new Memory(), fb).connect("OLD", "", "", ""));
        assertEquals(List.of("GET /me"), fb.calls);
    }

    private static FacebookPage connected(Memory vault, Fake fb) throws Exception {
        vault.put("facebook", new JSONObject().put("token", "PT").put("page_id", "42").put("page_name", "My Bakery")
                .put("status", "connected"));
        return new FacebookPage(vault, fb);
    }

    @Test public void postsGoToThePagesFeedWithItsToken() throws Exception {
        Fake fb = new Fake();
        fb.answers.put("POST /42/feed", new JSONObject().put("id", "42_777"));
        fb.answers.put("GET /42_777", new JSONObject().put("permalink_url", "https://www.facebook.com/42/posts/777"));
        JSONObject out = connected(new Memory(), fb).post("صباح الخير", "https://example.com/menu");
        JSONObject data = out.getJSONObject("data");
        assertEquals("42_777", data.getString("id"));
        assertEquals("https://www.facebook.com/42/posts/777", data.getString("url"));
        assertEquals("صباح الخير", fb.fields.get(0).get("message"));
        assertEquals("https://example.com/menu", fb.fields.get(0).get("link"));
        assertEquals("PT", fb.fields.get(0).get("access_token"));
        assertFalse(out.toString().contains("\"PT\""));
    }

    @Test public void aPostIsChecked() throws Exception {
        Fake fb = new Fake();
        FacebookPage fp = connected(new Memory(), fb);
        assertThrows(IllegalArgumentException.class, () -> fp.post("  ", ""));
        assertThrows(IllegalArgumentException.class, () -> fp.post("hi", "javascript:alert(1)"));
        assertThrows(IllegalStateException.class, () -> new FacebookPage(new Memory(), fb).post("hi", ""));
        assertTrue(fb.calls.isEmpty());
    }

    @Test public void anExpiredTokenMarksThePageForReconnecting() throws Exception {
        Memory vault = new Memory();
        Fake fb = new Fake();
        fb.answers.put("POST /42/feed", new FacebookPage.GraphError(190, "Facebook: Session has expired"));
        FacebookPage fp = connected(vault, fb);
        assertThrows(FacebookPage.GraphError.class, () -> fp.post("hi", ""));
        assertEquals("reauthorize", fp.status().getString("status"));
        IllegalStateException again = assertThrows(IllegalStateException.class, () -> fp.post("hi", ""));
        assertTrue(again.getMessage().contains("connect it again"));
        assertEquals(1, fb.calls.size());                                 // the second asked Facebook nothing
    }

    @Test public void recentPostsAreListedForTheNextRun() throws Exception {
        Fake fb = new Fake();
        fb.answers.put("GET /42/posts", new JSONObject().put("data", new JSONArray()
                .put(new JSONObject().put("id", "42_1").put("message", "أول منشور").put("created_time", "2026-10-23T08:00:00+0000"))));
        JSONObject out = connected(new Memory(), fb).recent(500);
        assertEquals("أول منشور", out.getJSONObject("data").getJSONArray("posts").getJSONObject(0).getString("message"));
        assertEquals("50", fb.fields.get(0).get("limit"));                // at most 50
    }

    @Test public void facebooksErrorsAreRead() throws Exception {
        try {
            FacebookPage.answer(400, "{\"error\":{\"message\":\"(#200) Permissions error\",\"code\":200}}");
            fail("an error answer");
        } catch (FacebookPage.GraphError e) {
            assertEquals(200, e.code);
            assertEquals("Facebook: (#200) Permissions error", e.getMessage());
        }
        assertEquals("1", FacebookPage.answer(200, "{\"id\":\"1\"}").getString("id"));
        assertThrows(FacebookPage.GraphError.class, () -> FacebookPage.answer(502, "<html>bad gateway</html>"));
        assertEquals("message=%D9%85%D8%B1%D8%AD%D8%A8%D8%A7&a=b%26c",
                FacebookPage.form(new String[][]{{"message", "مرحبا"}, {"a", "b&c"}}));
    }
}
