package dev.newal.code.lite;

import java.net.URI;
import java.net.URLEncoder;
import java.util.Locale;
import java.util.regex.Pattern;

/** The addresses the browser pane opens: web pages only (http and https), never file:, javascript: or intent:. */
final class BrowserAddress {
    private static final Pattern WEB = Pattern.compile("(?i)https?://\\S+");
    private static final Pattern LOCAL = Pattern.compile("(?i)(localhost|127\\.0\\.0\\.1)(:\\d{1,5})?(/\\S*)?");
    private static final Pattern HOST = Pattern.compile("[^\\s/:]+\\.[A-Za-z]{2,}(:\\d{1,5})?(/\\S*)?");
    static final String SEARCH = "https://duckduckgo.com/?q=";

    private BrowserAddress() {
    }

    /** What the agent asked to open: a web address, with http:// or https:// added to a bare host. */
    static String forAgent(String input) {
        String s = input == null ? "" : input.trim();
        String url = web(s);
        if (url == null) {
            throw new IllegalArgumentException("only web pages open in the browser (http or https): " + s);
        }
        return url;
    }

    /** What the user typed in the address field: a web address, or else a search for the words. */
    static String forUser(String input) {
        String s = input == null ? "" : input.trim();
        if (s.isEmpty()) {
            return "";
        }
        String url = web(s);
        if (url != null) {
            return url;
        }
        try {
            return SEARCH + URLEncoder.encode(s, "UTF-8");   // (the Charset overload needs Android 13)
        } catch (java.io.UnsupportedEncodingException e) {
            throw new IllegalStateException(e);
        }
    }

    private static String web(String s) {
        String url = null;
        if (WEB.matcher(s).matches()) {
            url = s;
        } else if (LOCAL.matcher(s).matches()) {
            url = "http://" + s;
        } else if (HOST.matcher(s).matches()) {
            url = "https://" + s;
        }
        if (url == null) {
            return null;
        }
        try {
            URI uri = new URI(url);
            String scheme = uri.getScheme() == null ? "" : uri.getScheme().toLowerCase(Locale.ROOT);
            if (!("http".equals(scheme) || "https".equals(scheme)) || uri.getHost() == null) {
                return null;
            }
        } catch (Exception e) {
            return null;
        }
        return url;
    }
}
