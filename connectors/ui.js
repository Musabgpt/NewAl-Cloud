// Additive connector panel. Original app.js, plugins, skills, terminal and review remain in place.
(() => {
  "use strict";
  const ar = () => document.documentElement.lang.startsWith("ar");
  const tr = (en, arabic) => ar() ? arabic : en;
  const labels = {
    connected: ["Connected", "متصل"], authorizing: ["Waiting for authorization", "بانتظار التفويض"],
    testing: ["Testing connection", "جارٍ اختبار الاتصال"], disconnected: ["Disconnected", "غير متصل"],
    not_configured: ["Deployment required", "يحتاج تفعيل الخدمة"], error: ["Connection failed", "فشل الاتصال"],
    reauthorize: ["Reconnect required", "يحتاج إعادة تفويض"], permission_required: ["Permission required", "يحتاج صلاحية"],
    unavailable: ["Unavailable on this host", "غير متاح على هذا الجهاز"]
  };
  let timer, active = false, pending = false, requesting = false;
  async function api(path, body) {
    const response = await fetch(path, { method: body ? "POST" : "GET", credentials: "same-origin",
      headers: body ? {"Content-Type": "application/json"} : {}, body: body ? JSON.stringify(body) : undefined });
    const result = await response.json();
    if (!response.ok || result.error || result.ok === false) throw new Error(result.error || "Connection failed");
    return result;
  }
  function element(tag, text, className) {
    const node = document.createElement(tag);
    if (text) node.textContent = text;
    if (className) node.className = className;
    return node;
  }
  async function refresh() {
    if (!active || requesting || pending) return;
    requesting = true;
    const list = document.querySelector("#connector-list"), message = document.querySelector("#connector-message");
    try {
      const result = await api("/api/connectors");
      if (!active) return;
      list.replaceChildren();
      for (const item of result.connectors) {
        const row = element("section", "", "connector-card"), detail = element("div");
        detail.append(element("strong", item.name));
        const label = labels[item.status] || [item.status, item.status];
        detail.append(element("div", tr(...label), "connector-state " + (item.status === "connected" ? "connected" : "")));
        if (item.account) detail.append(element("div", item.account, "muted"));
        if (item.scopes) { const scopes = element("details"); scopes.append(element("summary", tr("Granted scopes", "الصلاحيات الممنوحة")), element("small", item.scopes)); detail.append(scopes); }
        if (item.error) detail.append(element("div", item.error, "muted"));
        row.append(detail);
        const actions = element("div", "", "connector-actions");
        const connect = element("button", tr("Connect", "اتصال"), "btn primary");
        connect.disabled = !item.configured || ["connected", "authorizing", "testing", "unavailable"].includes(item.status);
        connect.onclick = async () => {
          if (item.id === "termux" && window.NewAlPhone) {
            const phone = JSON.parse(NewAlPhone.status());
            if (!phone.termux.installed) { NewAlPhone.openUrl("https://f-droid.org/packages/com.termux/"); return; }
            if (!phone.termux.allowed) { NewAlPhone.termuxAllow(); return; }
          }
          await action("connect", item.id);
        };
        actions.append(connect);
        if (["connected", "reauthorize", "error", "testing"].includes(item.status)) {
          const test = element("button", tr("Test", "اختبار"), "btn");
          test.onclick = () => action(item.id === "termux" ? "connect" : "test", item.id);
          actions.append(test);
        }
        if (["connected", "authorizing", "testing", "reauthorize", "error"].includes(item.status)) {
          const disconnect = element("button", tr("Disconnect", "فصل"), "btn");
          disconnect.onclick = () => action("disconnect", item.id);
          actions.append(disconnect);
        }
        row.append(actions); list.append(row);
      }
    } catch (error) { if (message) message.textContent = error.message; }
    finally { requesting = false; }
  }
  async function action(op, provider) {
    if (pending) return;
    pending = true;
    document.querySelectorAll("#connector-list button").forEach(button => { button.disabled = true; });
    const message = document.querySelector("#connector-message");
    message.textContent = tr("Working…", "جارٍ التنفيذ…");
    try {
      const result = await api("/api/connectors/" + op, {provider});
      message.textContent = result.text || (result.status === "authorizing" ? tr("Approve in the browser, then return here.", "وافق في المتصفح ثم ارجع للتطبيق.") : "");
    } catch (error) { message.textContent = error.message; }
    finally { pending = false; await refresh(); }
  }
  function close() {
    active = false;
    clearInterval(timer);
    document.querySelector("#connector-dialog").hidden = true;
    document.querySelector("#open-connectors").focus();
  }
  window.openMusabConnectors = () => {
    active = true;
    document.querySelector("#connector-dialog").hidden = false;
    document.querySelector("#connector-close").focus();
    refresh(); clearInterval(timer); timer = setInterval(refresh, 2500);
  };
  document.addEventListener("DOMContentLoaded", () => {
    const button = element("button", tr("Connections", "الاتصالات"), "side-item");
    button.id = "open-connectors";
    button.onclick = window.openMusabConnectors;
    document.querySelector(".side-top").append(button);
    // GitHub's entry point uses the same browser connection flow.
    document.querySelector("#open-github").addEventListener("click", event => {
      event.preventDefault(); event.stopImmediatePropagation(); window.openMusabConnectors();
    }, true);
    const dialog = element("div", "", "modal");
    dialog.id = "connector-dialog"; dialog.hidden = true;
    dialog.setAttribute("role", "dialog"); dialog.setAttribute("aria-modal", "true"); dialog.setAttribute("aria-labelledby", "connector-heading");
    const card = element("div", "", "modal-card connector-panel"), head = element("header");
    const title = element("span", tr("MusabAI connections", "اتصالات MusabAI")); title.id = "connector-heading";
    const closeButton = element("button", "×", "icon-btn"); closeButton.id = "connector-close";
    closeButton.setAttribute("aria-label", tr("Close", "إغلاق")); closeButton.onclick = close;
    head.append(title, closeButton); card.append(head);
    card.append(element("p", tr("Connect your account in the browser. Connected means a live account test passed.", "اربط حسابك من المتصفح. حالة متصل تعني نجاح اختبار وصول فعلي."), "muted"));
    const message = element("p"); message.id = "connector-message"; message.setAttribute("role", "status"); card.append(message);
    const list = element("div"); list.id = "connector-list"; card.append(list); dialog.append(card); document.body.append(dialog);
    dialog.addEventListener("keydown", event => {
      if (event.key === "Escape") { event.stopPropagation(); close(); }
      if (event.key === "Tab") {
        const focusable = [...dialog.querySelectorAll("button:not(:disabled), summary")];
        const first = focusable[0], last = focusable[focusable.length - 1];
        if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
        else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
      }
    });
    dialog.onclick = event => { if (event.target === dialog) close(); };
    window.addEventListener("focus", refresh);
  });
})();
