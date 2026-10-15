package dev.newal.code.lite;

import java.util.Locale;

/**
 * Text compared the way people type it: lower case, the Arabic letter forms people write interchangeably folded into
 * one (أ إ آ ٱ to ا, ة to ه, ى to ي), the diacritics and the tatweel removed, Arabic-Indic digits made 0-9, and runs of
 * spaces made one. "الاعدادات" then finds the app called "الإعدادات", and "ارسال" the button "إرسال". The same rules as
 * phone_fast._norm and Apache Lucene's Arabic normalizer (after Larkey et al., SIGIR 2002). When nothing matches that
 * way, a match without the article ال is tried (bare): "الكاميرا" finds "كاميرا".
 */
final class TextFold {
    private TextFold() {
    }

    static String fold(CharSequence text) {
        if (text == null) {
            return "";
        }
        String s = text.toString().toLowerCase(Locale.ROOT);
        StringBuilder out = new StringBuilder(s.length());
        boolean space = false;
        for (int i = 0; i < s.length(); i++) {
            char c = s.charAt(i);
            if ((c >= 'ً' && c <= 'ْ') || c == 'ٰ' || c == 'ـ') {
                continue;                       // harakat, the dagger alef, the tatweel
            }
            switch (c) {
                case 'أ':                  // أ
                case 'إ':                  // إ
                case 'آ':                  // آ
                case 'ٱ':                  // ٱ
                    c = 'ا';               // ا
                    break;
                case 'ة':                  // ة
                    c = 'ه';               // ه
                    break;
                case 'ى':                  // ى
                    c = 'ي';               // ي
                    break;
                default:
                    break;
            }
            if (c >= '٠' && c <= '٩') {
                c = (char) ('0' + (c - '٠'));    // Arabic-Indic digits: ٣ is 3
            } else if (c >= '۰' && c <= '۹') {
                c = (char) ('0' + (c - '۰'));    // the Persian and Urdu forms: ۳ is 3
            }
            if (Character.isWhitespace(c)) {
                if (out.length() > 0 && !space) {
                    out.append(' ');
                }
                space = true;
                continue;
            }
            space = false;
            out.append(c);
        }
        int n = out.length();
        if (n > 0 && out.charAt(n - 1) == ' ') {
            out.setLength(n - 1);
        }
        return out.toString();
    }

    /**
     * The text folded, its words without the article ال: "الكاميرا" -> "كاميرا", "الساعة" -> "ساعه". Only a real article
     * goes: one written with a bare alef ("إلغاء" and "ألوان" keep their first letters), and only when three letters or
     * more are left (Larkey's light stemming keeps short words whole: "الله" stays). For a second try, when the folded
     * text matched nothing.
     */
    static String bare(CharSequence text) {
        if (text == null) {
            return "";
        }
        StringBuilder out = new StringBuilder(text.length());
        for (String w : text.toString().trim().split("\\s+")) {
            String f = fold(w);
            if (w.startsWith("ال") && f.length() >= 5) {
                f = f.substring(2);
            }
            if (!f.isEmpty()) {
                if (out.length() > 0) {
                    out.append(' ');
                }
                out.append(f);
            }
        }
        return out.toString();
    }

    /**
     * The folded text with each number made one "#": "Inbox (12)" and "Inbox (13)" alike, a clock or a counter that
     * ticked on the same item. Empty when no letter is left, so a number alone ("14") is never taken for another.
     */
    static String withoutNumbers(CharSequence text) {
        String f = fold(text);
        StringBuilder out = new StringBuilder(f.length());
        boolean letter = false;
        for (int i = 0; i < f.length(); i++) {
            char c = f.charAt(i);
            if (!Character.isDigit(c)) {
                out.append(c);
                letter |= Character.isLetter(c);
            } else if (out.length() == 0 || out.charAt(out.length() - 1) != '#') {
                out.append('#');
            }
        }
        return letter ? out.toString() : "";
    }
}
