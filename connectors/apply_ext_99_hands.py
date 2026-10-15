"""The phone does more per call (hands.py: send, search, and a tap that scrolls to its text), Arabic matching takes
digits and the article ال in its stride, and the coding test measures stability (stability.py: pass^k)."""
import shutil


def apply(src, package, replace):
    for name in ("hands.py", "stability.py", "ext_hands_tests.py"):
        shutil.copyfile(src / name, package / name)

    # the compound actions wrap the phone tool last, around the screen check and phone_fast
    replace(package / "tools.py", "_task_state.install()\n",
            "_task_state.install()\nfrom . import hands as _hands\n_hands.install()\n")

    # Arabic as people type it, the same in Python as in the app (TextFold): Arabic-Indic digits are digits, alef wasla
    # and the dagger alef fold like the other alef forms, and a second try drops the article ال
    pf = package / "phone_fast.py"
    replace(pf, "def _norm(text):\n",
            'DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")\n\n\ndef _norm(text):\n')
    replace(pf, '    t = t.replace("أ", "ا").replace("إ", "ا").replace("آ", "ا").replace("ة", "ه").replace("ى", "ي")\n',
            '    t = t.replace("أ", "ا").replace("إ", "ا").replace("آ", "ا").replace("ٱ", "ا").replace("ة", "ه")'
            '.replace("ى", "ي")\n'
            "    t = t.replace(chr(0x670), \"\").translate(DIGITS)     # the dagger alef; ٣ is 3 (as TextFold)\n")
    replace(pf, "def _words(text):\n",
            "def _bare(text):\n"
            '    """The text folded, its words without the article ال (TextFold.bare): "الكاميرا" -> "كاميرا". Only a real\n'
            '    article, written with a bare alef ("إلغاء" keeps its first letters), and only when three letters or more\n'
            '    are left ("الله" stays)."""\n'
            "    out = []\n"
            "    for w in str(text or \"\").split():\n"
            "        f = _norm(w)\n"
            '        if w.startswith("ال") and len(f) >= 5:\n'
            "            f = f[2:]\n"
            "        if f:\n"
            "            out.append(f)\n"
            '    return " ".join(out)\n\n\n'
            "def _words(text):\n")
    replace(pf, "        hit = next((v for k, v in APP_NAMES.items() if _norm(k) == folded), None)\n    return hit or name\n",
            "        hit = next((v for k, v in APP_NAMES.items() if _norm(k) == folded), None)\n"
            "    if hit is None:\n"
            '        bare = _bare(key)          # and without the article: "كاميرا" is "الكاميرا"\n'
            "        hit = next((v for k, v in APP_NAMES.items() if _bare(k) == bare), None) if bare else None\n"
            "    return hit or name\n")

    java = package.parent.parent / "android-lite/app/src/main/java/dev/newal/code/lite"
    if java.is_dir():
        replace(java / "Phone.java",
                '        if (best == null) {\n'
                '            throw new IllegalArgumentException("no app called \\"" + name + "\\" (action apps lists them)");\n'
                '        }\n',
                "        if (best == null) {\n"
                "            // a second try without the article: \"الكاميرا\" opens the app called \"كاميرا\", and the other way\n"
                "            String bareWant = TextFold.bare(name);\n"
                "            for (String[] app : bareWant.isEmpty() ? new ArrayList<String[]>() : launchable(ctx)) {\n"
                "                String label = TextFold.bare(app[0]);\n"
                "                int s = label.equals(bareWant) ? 3 : label.startsWith(bareWant) ? 2\n"
                "                        : label.contains(bareWant) ? 1 : 0;\n"
                "                if (s > score) {\n"
                "                    best = app;\n"
                "                    score = s;\n"
                "                }\n"
                "            }\n"
                "        }\n"
                '        if (best == null) {\n'
                '            throw new IllegalArgumentException("no app called \\"" + name + "\\" (action apps lists them)");\n'
                '        }\n')
        replace(java / "PhoneControlService.java",
                '            if (idx < 0) {\n'
                '                throw new IllegalArgumentException("nothing on the screen says \\"" + a.optString("text") + "\\"");\n'
                '            }\n',
                "            if (idx < 0) {\n"
                "                // a second try without the article: \"الاعدادات\" taps \"إعدادات\", and the other way round\n"
                "                String bareWant = TextFold.bare(a.optString(\"text\"));\n"
                "                for (int i = 0; i < items.size() && !bareWant.isEmpty(); i++) {\n"
                "                    String w = TextFold.bare(words(items.get(i)));\n"
                "                    int s = w.equals(bareWant) ? 3 : w.startsWith(bareWant) ? 2 : w.contains(bareWant) ? 1 : 0;\n"
                "                    if (s > score) {\n"
                "                        score = s;\n"
                "                        idx = i;\n"
                "                    }\n"
                "                }\n"
                "            }\n"
                '            if (idx < 0) {\n'
                '                throw new IllegalArgumentException("nothing on the screen says \\"" + a.optString("text") + "\\"");\n'
                '            }\n')

    # the model hears of the compound actions where it learns the phone
    lp = package / "agent_prompt_lean.md"
    replace(lp, "- Tap by number from the latest screen (item=7), or by text. To type, tap the field first, then type. "
                "After typing a message, tap the send button.\n",
            "- Tap by number from the latest screen (item=7), or by text (a text further down a list is scrolled to). "
            "To send a message in an open chat, use send with the text: it types it into the message field and taps "
            "Send in one call. To type anything else, tap the field first, then type.\n")
    replace(lp, "- Inside an app: tap the search icon, type, then tap the matching result.\n",
            "- To search inside an app, use search with the text: it finds the search field, types and presses enter. "
            "Then tap the matching result.\n")

    # the coding test, k times over: pass@1 and pass^k
    bm = package / "benchmark.py"
    replace(bm, '    ap.add_argument("--out", default="")\n',
            '    ap.add_argument("--out", default="")\n'
            '    ap.add_argument("--repeat", type=int, default=1, help="each task this many times: pass@1 and pass^k")\n')
    replace(bm, '    summary = run(a.model, a.tasks)\n'
                '    print("TOTAL %.1f s, %d/%d passed" % (summary["seconds"], summary["passed"], summary["tasks"]))\n',
            '    if a.repeat > 1:\n'
            '        from . import stability\n'
            '        summary = stability.run(a.model, a.tasks, a.repeat)\n'
            '        print(stability.line(summary))\n'
            '    else:\n'
            '        summary = run(a.model, a.tasks)\n'
            '        print("TOTAL %.1f s, %d/%d passed" % (summary["seconds"], summary["passed"], summary["tasks"]))\n')

    with open(package / "claude_parity_tests.py", "a", encoding="utf-8") as f:
        f.write("\nfrom .ext_hands_tests import HandsTests  # noqa: E402,F401 - run with the parity tests in CI\n")
