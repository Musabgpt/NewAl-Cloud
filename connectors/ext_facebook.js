/* MusabAI: Connections > Facebook Page. The access token goes from this card straight to the app's Keystore vault
   (window.NewAlPhone.facebookConnect -> FacebookPage.java), never through the engine; the card shows the Page's name,
   whether its token lasts, and what Facebook said. With it the agent and scheduled tasks post on the Page without
   opening Facebook (facebook_page.py). */
(function () {
  "use strict";
  const ar = () => (document.documentElement.lang || "").startsWith("ar");
  const t = (en, a) => (ar() ? a : en);
  const node = (tag, text) => { const e = document.createElement(tag); if (text) e.textContent = text; return e; };
  const phone = () => (window.NewAlPhone && typeof window.NewAlPhone.facebookConnect === "function" ? window.NewAlPhone : null);
  const parse = s => { try { return JSON.parse(s || "{}"); } catch (_) { return { ok: false, error: String(s) }; } };
  const STEPS = [
    ["Sign in at developers.facebook.com with your Facebook account, then My Apps > Create App (any name; if it asks what for, pick managing a Page).",
      "فوت على developers.facebook.com بحساب فيسبوك تبعك، وبعدين My Apps ← Create App (أي اسم، وإذا سألك لشو، اختار إدارة صفحة)."],
    ["In the app: Settings > Basic. Copy the App ID and the App Secret into the two boxes above (under “make it last”).",
      "جوا التطبيق: Settings ← Basic. انسخ App ID و App Secret وحطهم بالخانتين فوق (تحت «لتخليه ما يخلص»)."],
    ["Open developers.facebook.com/tools/explorer, pick your app, add the permissions pages_show_list, pages_read_engagement and pages_manage_posts, press Generate Access Token and choose your Page.",
      "افتح developers.facebook.com/tools/explorer، اختار تطبيقك، ضيف الصلاحيات pages_show_list و pages_read_engagement و pages_manage_posts، اكبس Generate Access Token واختار صفحتك."],
    ["Copy the token into “Access token” and press Connect. “Lasts” means it never expires.",
      "انسخ الرمز لخانة «رمز الوصول» واكبس «ربط». إذا طلع «ما بيخلص» يعني ما بيخلص أبداً."],
    ["Switch the app to Live in its dashboard: while it is in development, its posts show to you only.",
      "حوّل التطبيق لـ Live من لوحته: طول ما هو بوضع التطوير، منشوراته بتبين إلك بس."],
  ];

  function render(card, d) {
    const state = card.querySelector(".fb-state");
    const msg = card.querySelector(".fb-msg");
    if (!phone()) {
      state.textContent = t("Available in the Android app.", "متاح بتطبيق أندرويد.");
      card.querySelectorAll("button").forEach(b => { b.disabled = true; });
      return;
    }
    const on = d && d.has_credentials;
    let line = !on ? t("Not connected", "غير متصل")
      : d.status === "reauthorize" ? t("The token expired: connect again", "الرمز خلص: اربط من جديد")
      : t("Connected: ", "متصل: ") + (d.account || "");
    if (on && d.status !== "reauthorize") {
      line += " · " + (d.lasting ? t("lasts", "ما بيخلص")
        : d.expires_at ? t("expires ", "بيخلص ") + new Date(d.expires_at * 1000).toLocaleString(ar() ? "ar" : undefined)
        : t("may expire: add the App ID and secret", "ممكن يخلص: ضيف App ID و Secret"));
    }
    state.textContent = line;
    card.querySelector("[data-fb=test]").disabled = !on;
    card.querySelector("[data-fb=off]").disabled = !on;
    if (d && d.ok === false && d.error) msg.textContent = d.error;
    else if (d && d.warning) msg.textContent = "⚠ " + d.warning;
  }

  function build(panel) {
    const card = node("section");
    card.className = "connector-card facebook-page";
    card.dataset.lang = ar() ? "ar" : "en";
    card.append(node("h3", t("Facebook Page", "صفحة فيسبوك")));
    card.append(node("p", t(
      "Post on your Page without opening Facebook: scheduled tasks post with the screen off. Pages only (Facebook lets no app post on a personal profile). The token stays encrypted on this phone and never reaches the model.",
      "انشر على صفحتك بلا ما ينفتح فيسبوك: المهام المجدولة بتنشر والشاشة مطفية. للصفحات بس (فيسبوك ما بيسمح لأي تطبيق ينشر على الحساب الشخصي). الرمز بيضل مشفّر على هالجوال وما بيوصل للموديل.")));
    const state = node("p"); state.className = "fb-state";
    const token = node("input"); token.type = "password"; token.autocomplete = "off";
    token.placeholder = t("Access token", "رمز الوصول (Access token)");
    const more = node("details");
    more.append(node("summary", t("Make it last (App ID and secret), or name the Page", "لتخليه ما يخلص (App ID و Secret)، أو اسم الصفحة")));
    const appId = node("input"); appId.placeholder = "App ID"; appId.autocomplete = "off"; appId.inputMode = "numeric";
    const secret = node("input"); secret.type = "password"; secret.placeholder = "App Secret"; secret.autocomplete = "off";
    const page = node("input"); page.placeholder = t("The Page's name (if you manage several)", "اسم الصفحة (إذا عندك أكتر من وحدة)");
    more.append(appId, secret, page);
    const acts = node("div"); acts.className = "connector-actions";
    const connect = node("button", t("Connect", "ربط")); connect.type = "button"; connect.className = "btn primary"; connect.dataset.fb = "connect";
    const test = node("button", t("Test", "اختبار")); test.type = "button"; test.className = "btn"; test.dataset.fb = "test";
    const off = node("button", t("Disconnect", "فصل")); off.type = "button"; off.className = "btn"; off.dataset.fb = "off";
    acts.append(connect, test, off);
    const msg = node("p"); msg.className = "fb-msg"; msg.setAttribute("role", "status");
    const how = node("details");
    how.append(node("summary", t("How do I get the token?", "كيف بجيب الرمز؟")));
    const steps = node("ol");
    STEPS.forEach(s => steps.append(node("li", t(s[0], s[1]))));
    how.append(steps);
    card.append(state, token, more, acts, msg, how);
    panel.insertBefore(card, document.querySelector("#connector-list"));

    const run = (fn, done) => {
      const p = phone();
      if (!p) return;
      msg.textContent = t("Asking Facebook…", "عم إسأل فيسبوك…");
      card.querySelectorAll("button").forEach(b => { b.disabled = true; });
      setTimeout(() => {               // the bridge call waits for Facebook: let the message show first
        const d = parse(fn(p));
        msg.textContent = d.ok === false ? "" : (done || "");
        if (d.ok !== false) { token.value = ""; secret.value = ""; }
        connect.disabled = false;
        render(card, d.ok === false ? Object.assign(parse(p.facebookStatus()), { ok: false, error: d.error }) : d);
      }, 30);
    };
    connect.onclick = () => {
      if (!token.value.trim()) { msg.textContent = t("Paste the access token first.", "الصق رمز الوصول أول."); return; }
      run(p => p.facebookConnect(token.value, appId.value, secret.value, page.value), t("Connected.", "تم الربط."));
    };
    test.onclick = () => run(p => p.facebookTest(), t("It works.", "شغّال."));
    off.onclick = () => run(p => p.facebookDisconnect(), t("Disconnected on this phone.", "انفصل على هالجوال."));
    render(card, phone() ? parse(phone().facebookStatus()) : null);
    return card;
  }

  // built when Connections opens (in the interface's language by then), again when the language changed since
  function boot() {
    const panel = document.querySelector(".connector-panel");
    if (!panel || !document.querySelector("#connector-list")) return;
    const old = panel.querySelector(".facebook-page");
    if (old && old.dataset.lang === (ar() ? "ar" : "en")) return;
    if (old) old.remove();
    build(panel);
  }
  document.addEventListener("click", e => {
    if (e.target && e.target.closest && e.target.closest("#open-connectors")) setTimeout(boot, 0);
  }, true);
  setTimeout(boot, 4000);
  window.MusabFacebookPage = { boot };
})();
