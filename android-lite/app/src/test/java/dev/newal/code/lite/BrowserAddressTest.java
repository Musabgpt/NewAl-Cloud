package dev.newal.code.lite;

import org.junit.Test;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertTrue;
import static org.junit.Assert.fail;

public class BrowserAddressTest {
    @Test public void webAddressesOpenAsGiven() {
        assertEquals("https://github.com/Musabgpt", BrowserAddress.forAgent("https://github.com/Musabgpt"));
        assertEquals("http://127.0.0.1:3000/", BrowserAddress.forAgent(" http://127.0.0.1:3000/ "));
    }

    @Test public void bareHostsGetTheirScheme() {
        assertEquals("https://github.com", BrowserAddress.forAgent("github.com"));
        assertEquals("https://example.org/a?b=1", BrowserAddress.forAgent("example.org/a?b=1"));
        assertEquals("http://localhost:5173", BrowserAddress.forAgent("localhost:5173"));
        assertEquals("http://127.0.0.1:8080/app", BrowserAddress.forUser("127.0.0.1:8080/app"));
    }

    @Test public void onlyWebPagesOpenForTheAgent() {
        for (String bad : new String[] {"javascript:alert(1)", "file:///sdcard/secret.txt", "intent://x#Intent;end",
                "content://media/1", "about:config", "", "how to build an apk", "https://"}) {
            try {
                BrowserAddress.forAgent(bad);
                fail("opened " + bad);
            } catch (IllegalArgumentException expected) {
                assertTrue(expected.getMessage().contains("http"));
            }
        }
    }

    @Test public void wordsTypedByTheUserAreASearch() {
        assertEquals(BrowserAddress.SEARCH + "android+apk+build", BrowserAddress.forUser("android apk build"));
        assertEquals(BrowserAddress.SEARCH + "%D8%B7%D9%82%D8%B3", BrowserAddress.forUser("طقس"));
        assertEquals(BrowserAddress.SEARCH + "javascript%3Aalert%281%29", BrowserAddress.forUser("javascript:alert(1)"));
        assertEquals("", BrowserAddress.forUser("   "));
    }
}
