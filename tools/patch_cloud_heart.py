from pathlib import Path
p = Path("android-lite/app/src/main/java/dev/newal/code/lite/Setup.java")
s = p.read_text()
needle = 'env.put("NEWAL_TERMUX_PORT", String.valueOf(Termux.PORT));'
insert = needle + '''
        // NewAl-Cloud: keep Action #43 unchanged; replace only the model/API heart.
        File cfg = new File(home, ".newal-code/config.json");
        if (!cfg.exists()) {
            cfg.getParentFile().mkdirs();
            write(cfg, "{\\n" +
                    " \\"model\\": \\"kilo-auto/free\\",\\n" +
                    " \\"models\\": { \\"kilo-auto/free\\": {\\"id\\":\\"kilo-auto/free\\",\\"name\\":\\"FreeLLMAPI • Auto Free\\",\\"provider\\":\\"openai\\",\\"base_url\\":\\"https://api.kilo.ai/api/gateway\\",\\"model\\":\\"kilo-auto/free\\",\\"api_key\\":\\"\\",\\"context\\":256000} },\\n" +
                    " \\"mode\\": \\"auto-edit\\", \\"verify\\": true, \\"test_after_edit\\": true, \\"auto_context\\": true, \\"web\\": true\\n}");
        }'''
if needle not in s:
    raise SystemExit("Setup.java patch point not found")
if "kilo-auto/free" in s:
    raise SystemExit("Setup.java already patched")
p.write_text(s.replace(needle, insert, 1))
