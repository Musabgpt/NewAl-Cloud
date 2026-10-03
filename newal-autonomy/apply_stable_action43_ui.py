#!/usr/bin/env python3
from pathlib import Path
p=Path("desktop/newal_code/ui/app.js")
s=p.read_text(encoding="utf-8")

# GitHub: keep Action #43 GitHub UI, replace token entry on Android with the native browser OAuth bridge.
a=s.index("  async function githubSection(box, after) {")
b=s.index("  async function openClone()",a)
new=r'''  async function githubSection(box, after) {
    let a = {};
    try { a = await api("/api/github"); } catch (_) {}
    GITHUB.page = a.token_page;
    box.innerHTML = "";
    if (a.connected) {
      box.appendChild(h("div", "form-row", '<span>Connected' + (a.login ? " as <b>@" + esc(a.login) + "</b>" : "") +
        '</span><button class="btn" id="gh-clone">Clone a repository</button><button class="btn" id="gh-off">Disconnect</button>'));
      box.querySelector("#gh-clone").onclick = () => openClone();
      box.querySelector("#gh-off").onclick = async () => { await api("/api/github/disconnect", {}); githubSection(box); };
      return;
    }
    box.appendChild(h("div", "form-row", '<button class="btn primary" id="gh-on">Connect GitHub</button>' +
      '<span class="muted">Secure browser authorization. No GitHub token is pasted into MusabAI.</span>'));
    box.querySelector("#gh-on").onclick = async () => {
      const b=box.querySelector("#gh-on"); b.disabled=true; b.textContent="Opening GitHub…";
      try {
        if (!(window.NewAlPhone && NewAlPhone.githubLogin && NewAlPhone.githubSync))
          throw new Error("GitHub browser authorization is available in the MusabAI Android app.");
        if (NewAlPhone.githubLogin() !== "started") throw new Error("GitHub authorization could not start.");
        toast("GitHub opened. Approve access; MusabAI will finish automatically.",7000);
        for(let i=0;i<120;i++){
          await new Promise(r=>setTimeout(r,2000));
          const q=NewAlPhone.githubSync();
          if(q==="connected"){ toast("GitHub connected — no token was entered.",5000); githubSection(box,after); return; }
          if(/^failed|^sync failed|^server error/.test(q)) throw new Error(q);
        }
        throw new Error("GitHub authorization timed out. Open Connect GitHub again.");
      } catch(e) { b.disabled=false; b.textContent="Connect GitHub"; toast(e.message,9000); }
    };
  }
'''
s=s[:a]+new+s[b:]

# Cloud Session must use the normal Action #43 session engine in a standalone workspace.
a=s.index("  async function sendToCloud(text) {")
b=s.index("\n  }",a)+4
new=r'''  async function sendToCloud(text) {
    try {
      localStorage.setItem("nc.pref.env","cloud");
      const sid = await ensureSession();
      await api("/api/sessions/" + sid + "/send", {
        text: text,
        lang: (S.state && S.state.settings.lang) || ""
      });
    } catch (e) { toast("Cloud Session failed: " + e.message, 9000); }
  }'''
s=s[:a]+new+s[b:]
s=s.replace('$("#open-cloud").onclick = () => openCloud();',
            '$("#open-cloud").onclick = () => { localStorage.setItem("nc.pref.env","cloud"); updatePickers(); newThread(); $("#input").focus(); };')
s=s.replace('{ value: "cloud", title: "Cloud", sub: "On GitHub Actions, with the repository: review the diff here, apply it or open a pull request", checked: env === "cloud" }',
            '{ value: "cloud", title: "Cloud Session", sub: "Independent cloud workspace — no GitHub or Git remote required", checked: env === "cloud" }')

# MusabAI name only; no UI structure changes.
s=s.replace("NewAl Code","MusabAI")
p.write_text(s,encoding="utf-8")
