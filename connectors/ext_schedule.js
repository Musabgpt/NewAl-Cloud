/* MusabAI: scheduled tasks in the workspace bar (schedule.py).
   - ⏰ Tasks: the morning brief and the quiet check-in (on/off, their times), every scheduled task with its next run
     and last result (run now, pause, resume, remove, open its last run), and a form to add one.
   - The chat does the same in plain words ("كل يوم الساعة 8 لخصلي الأخبار"), or /schedule and /duet. */
(function () {
  "use strict";
  const $ = s => document.querySelector(s);
  const esc = s => String(s == null ? "" : s).replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const ar = () => (document.documentElement.lang || "").startsWith("ar") || (window.NCi18n && NCi18n.active && NCi18n.active());
  const t = (en, a) => (ar() ? a : en);
  const sid = () => (window.NewAlWorkspaceSession ? window.NewAlWorkspaceSession() : "");
  async function call(path, body) {
    const r = await fetch(path, body ? { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) } : undefined);
    const d = await r.json().catch(() => ({}));
    if (!r.ok || (d && d.error)) throw new Error((d && d.error) || "HTTP " + r.status);
    return d;
  }
  const say = msg => { const b = document.createElement("div"); b.className = "mf-toast"; b.innerHTML = '<div class="mf-tt">' + esc(msg) + "</div>";
    let box = $("#mf-toasts"); if (!box) { box = document.createElement("div"); box.id = "mf-toasts"; document.body.appendChild(box); }
    box.appendChild(b); setTimeout(() => b.remove(), 6000); };
  const when = ts => ts ? new Date(ts * 1000).toLocaleString(ar() ? "ar" : undefined, { weekday: "short", hour: "2-digit", minute: "2-digit", day: "numeric", month: "short" }) : "-";
  const last = { done: "✓", quiet: "🔕", stopped: "■", error: "⚠", running: "⏳" };

  function sheet() {
    let o = document.getElementById("musab-schedule");
    if (!o) {
      o = document.createElement("div");
      o.id = "musab-schedule";
      o.className = "musab-preview";
      o.innerHTML = '<div class="mp-card"><header><span class="mp-title"></span><button type="button" class="mp-x" title="Close">×</button></header><div class="mp-body mf-body"></div></div>';
      document.body.appendChild(o);
      o.querySelector(".mp-x").onclick = () => { o.hidden = true; clearInterval(o._timer); };
    }
    o.querySelector(".mp-title").textContent = t("Scheduled tasks", "المهام المجدولة");
    o.hidden = false;
    return o;
  }

  async function open() {
    const o = sheet();
    const body = o.querySelector(".mp-body");
    body.innerHTML =
      '<div class="mf-row ms-duet"><div class="mf-head"><b>' + t("Proactive assistant", "المساعد الاستباقي") + '</b><label><input type="checkbox" data-duet> ' + t("On", "مفعّل") + "</label></div>" +
      '<div class="mf-meta">' + t("A morning brief at", "ملخص الصبح الساعة") + ' <input type="time" value="08:00" data-brief> · ' + t("a check-in every", "تفقّد كل") +
      ' <select data-every><option value="1h">1h</option><option value="2h">2h</option><option value="3h" selected>3h</option><option value="6h">6h</option></select> ' +
      t("(08:00-22:00; it speaks only when something needs you)", "(٨ الصبح - ١٠ المسا؛ ما بيحكي إلا إذا في شي مهم)") + "</div></div>" +
      '<form class="mf-new ms-new" style="flex-wrap:wrap"><textarea rows="2" style="flex:1 1 100%" placeholder="' + esc(t("What should it do at that time? (e.g. summarize my WhatsApp notifications)", "شو يعمل بهداك الوقت؟ (مثلاً: لخصلي إشعارات واتساب)")) + '"></textarea>' +
      '<div class="mf-meta" style="flex:1 1 auto"><select data-kind><option value="daily">' + t("Every day", "كل يوم") + '</option><option value="weekly">' + t("Some days", "أيام محددة") +
      '</option><option value="every">' + t("Every…", "كل…") + '</option><option value="once">' + t("Once", "مرة وحدة") + "</option></select> " +
      '<input type="time" value="08:00" data-at> <input type="date" data-date hidden> <input type="text" size="10" placeholder="mon,fri" data-days hidden>' +
      ' <input type="text" size="4" value="3h" data-everyv hidden> <label><input type="checkbox" data-quiet> ' + t("Only if important", "بس إذا مهم") + "</label></div>" +
      '<button type="submit" class="mf-btn primary">' + t("Schedule", "جدول") + "</button></form><div class=\"mf-list\"></div>";
    const form = body.querySelector("form"), list = body.querySelector(".mf-list");
    const kind = form.querySelector("[data-kind]");
    const show = () => {
      const k = kind.value;
      form.querySelector("[data-at]").hidden = k === "every";
      form.querySelector("[data-date]").hidden = k !== "once";
      form.querySelector("[data-days]").hidden = k !== "weekly";
      form.querySelector("[data-everyv]").hidden = k !== "every";
    };
    kind.onchange = show;
    show();
    const need = () => { if (!sid()) { say(t("Open a thread in the project first.", "افتح محادثة في المشروع أولاً.")); return false; } return true; };
    form.onsubmit = async ev => {
      ev.preventDefault();
      const prompt = form.querySelector("textarea").value.trim();
      if (!prompt || !need()) return;
      const v = s => form.querySelector(s).value;
      try {
        const d = await call("/api/schedules/add", { session: sid(), prompt, kind: kind.value, at: v("[data-at]"), date: v("[data-date]"),
          days: v("[data-days]"), every: v("[data-everyv]"), quiet: form.querySelector("[data-quiet]").checked });
        form.querySelector("textarea").value = "";
        say("⏰ " + d.task.name + " — " + t("next", "التالي") + ": " + when(d.task.next));
        render();
      } catch (e) { say(e.message); }
    };
    const duetBox = body.querySelector("[data-duet]");
    const setDuet = async () => {
      if (!need()) { duetBox.checked = !duetBox.checked; return; }
      try {
        await call("/api/schedules/duet", { session: sid(), on: duetBox.checked, at: body.querySelector("[data-brief]").value || "08:00",
          every: body.querySelector("[data-every]").value });
        render();
      } catch (e) { say(e.message); }
    };
    duetBox.onchange = setDuet;
    body.querySelector("[data-brief]").onchange = () => { if (duetBox.checked) setDuet(); };
    body.querySelector("[data-every]").onchange = () => { if (duetBox.checked) setDuet(); };

    const render = async () => {
      let d;
      try { d = await call("/api/schedules"); } catch (e) { list.innerHTML = '<p class="mp-muted">' + esc(e.message) + "</p>"; return; }
      const tasks = d.tasks || [];
      duetBox.checked = tasks.some(x => x.preset === "brief" || x.preset === "checkin");
      if (!tasks.length) {
        list.innerHTML = '<p class="mp-muted">' + t("No scheduled tasks yet. Add one above, or tell the chat: \"every day at 8 summarize the news\".",
          "ما في مهام بعد. ضيف وحدة فوق، أو احكي بالمحادثة: «كل يوم الساعة 8 لخصلي الأخبار».") + "</p>";
        return;
      }
      list.innerHTML = "";
      tasks.forEach(x => {
        const row = document.createElement("div");
        row.className = "mf-row";
        const st = !x.enabled ? "⏸ " + t("paused", "متوقفة") : x.running ? "⏳ " + t("running", "تعمل") : x.waiting_unlock ? "🔒 " + t("unlock the phone", "افتح قفل الجوال") :
          x.pending ? "… " + t("due", "حان وقتها") : t("next", "التالي") + ": " + when(x.next);
        const l = x.last || {};
        row.innerHTML = '<div class="mf-head"><b>' + esc(x.name) + '</b><span class="mf-state">' + esc(st) + "</span></div>" +
          '<div class="mf-meta">' + esc(x.schedule) + (x.quiet ? " · 🔕 " + t("only if important", "بس إذا مهم") : "") + (x.phone ? " · 📱 " + t("uses the screen", "بيستعمل الشاشة") : "") + "</div>" +
          (l.state && l.state !== "running" ? '<div class="mf-answer">' + (last[l.state] || "") + " " + esc(when(l.time)) + (l.answer ? " — " + esc(String(l.answer).slice(0, 220)) : "") + "</div>" : "") +
          '<div class="mf-acts"><button type="button" class="mf-btn primary" data-a="run">' + t("Run now", "شغّل الآن") + "</button>" +
          '<button type="button" class="mf-btn" data-a="' + (x.enabled ? "pause" : "resume") + '">' + (x.enabled ? t("Pause", "إيقاف") : t("Resume", "تشغيل")) + "</button>" +
          (l.session ? '<button type="button" class="mf-btn" data-a="open">' + t("Open last run", "افتح آخر تشغيل") + "</button>" : "") +
          '<button type="button" class="mf-btn danger" data-a="remove">' + t("Remove", "احذف") + "</button></div>";
        row.querySelectorAll("button").forEach(b => b.onclick = async () => {
          try {
            if (b.dataset.a === "open") { o.hidden = true; if (window.NewAlOpenSession) window.NewAlOpenSession(l.session); return; }
            if (b.dataset.a === "remove" && !confirm(t("Remove this task?", "حذف هالمهمة؟"))) return;
            await call("/api/schedules/" + b.dataset.a, { id: x.id });
            render();
          } catch (e) { say(e.message); }
        });
        list.appendChild(row);
      });
    };
    clearInterval(o._timer);
    o._timer = setInterval(() => { if (!o.hidden && !document.hidden) render(); }, 10000);
    render();
  }

  function addButton() {
    const anchor = $("#musab-agents-btn") || $("#musab-live-btn") || $("#musab-vscode") || $("#musab-modes");
    if (!anchor || $("#musab-schedule-btn")) return;
    const b = document.createElement("button");
    b.type = "button";
    b.id = "musab-schedule-btn";
    b.className = "musab-vscode";
    b.title = "Tasks";
    b.setAttribute("aria-label", "Tasks");
    b.innerHTML = '<span class="mb-ic" aria-hidden="true">⏰</span><span class="mb-tx">' + t("Tasks", "المهام") + "</span>";
    b.onclick = open;
    anchor.after(b);
  }

  window.MusabSchedule = { open };
  const boot = () => addButton();
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot); else boot();
  setTimeout(boot, 2000);
  setTimeout(boot, 4600);
})();
