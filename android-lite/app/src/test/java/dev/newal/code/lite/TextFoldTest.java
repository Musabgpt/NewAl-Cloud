package dev.newal.code.lite;

import org.junit.Test;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertNotEquals;

public class TextFoldTest {
    @Test public void arabicLetterFormsPeopleTypeInterchangeablyMatch() {
        assertEquals(TextFold.fold("الإعدادات"), TextFold.fold("الاعدادات"));
        assertEquals(TextFold.fold("إرسال"), TextFold.fold("ارسال"));
        assertEquals(TextFold.fold("آلة حاسبة"), TextFold.fold("الة حاسبه"));
        assertEquals(TextFold.fold("مستشفى"), TextFold.fold("مستشفي"));
        assertEquals(TextFold.fold("مكتبة"), TextFold.fold("مكتبه"));
    }

    @Test public void diacriticsTatweelCaseAndSpacesDoNotMatter() {
        assertEquals("محمد", TextFold.fold("مُحَمَّد"));
        assertEquals("محمد", TextFold.fold("مـحـمـد"));
        assertEquals("whatsapp business", TextFold.fold("  WhatsApp \n Business "));
    }

    @Test public void differentWordsStayDifferent() {
        assertNotEquals(TextFold.fold("واتساب"), TextFold.fold("تيليجرام"));
        assertEquals("", TextFold.fold(null));
    }

    @Test public void arabicIndicDigitsAreDigits() {
        assertEquals(TextFold.fold("١٢:٣٠"), TextFold.fold("12:30"));
        assertEquals(TextFold.fold("۱۲"), TextFold.fold("12"));
        assertEquals("الصفحه 3", TextFold.fold("الصفحة ٣"));
    }

    @Test public void theArticleGoesOnlyWhenItIsOne() {
        assertEquals(TextFold.bare("الكاميرا"), TextFold.bare("كاميرا"));
        assertEquals("ساعه", TextFold.bare("الساعة"));
        assertEquals("اعدادات واي فاي", TextFold.bare("الإعدادات واي فاي"));
        assertEquals("الغاء", TextFold.bare("إلغاء"));          // a hamza: no article to drop
        assertEquals("الوان", TextFold.bare("ألوان"));
        assertEquals("الله", TextFold.bare("الله"));             // three letters would not be left
        assertEquals("", TextFold.bare(null));
    }

    @Test public void aNumberThatTickedLeavesTheSameItem() {
        assertEquals(TextFold.withoutNumbers("Inbox (12)"), TextFold.withoutNumbers("Inbox (13)"));
        assertEquals(TextFold.withoutNumbers("منذ ٥ دقائق"), TextFold.withoutNumbers("منذ 15 دقائق"));
        assertNotEquals(TextFold.withoutNumbers("Play"), TextFold.withoutNumbers("Pause"));
        assertNotEquals(TextFold.withoutNumbers("Ahmad 2"), TextFold.withoutNumbers("Sara 2"));
    }

    @Test public void aNumberAloneIsNeverTakenForAnother() {
        assertEquals("", TextFold.withoutNumbers("14"));
        assertEquals("", TextFold.withoutNumbers("12:45"));
        assertEquals("", TextFold.withoutNumbers(null));
    }
}
