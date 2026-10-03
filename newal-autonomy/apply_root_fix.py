#!/usr/bin/env python3
from pathlib import Path

p=Path("desktop/newal_code/ui/app.js")
if not p.exists():
    raise SystemExit("Action #43 app.js not found")

s=p.read_text(encoding="utf-8")

old_start=s.index("  async function githubSection(box, after) {")
old_end=s.index("  async function openClone()", old_start)
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
    box.appendChild(h("div", "form-row",
      '<button class="btn primary" id="gh-on">Connect GitHub</button>' +
      '<span class="muted">Secure browser authorization. No GitHub token is pasted into MusabAI.</span>'));
    box.querySelector("#gh-on").onclick = async () => {
      const b=box.querySelector("#gh-on");
      b.disabled=true; b.textContent="Opening GitHub…";
      try {
        if (!(window.NewAlPhone && NewAlPhone.githubLogin && NewAlPhone.githubSync))
          throw new Error("GitHub browser authorization is available in the MusabAI Android app.");
        const started=NewAlPhone.githubLogin();
        if (started !== "started") throw new Error(String(started));
        toast("GitHub opened. Approve access; MusabAI will finish automatically.",7000);
        for(let i=0;i<120;i++){
          await new Promise(r=>setTimeout(r,2000));
          const q=NewAlPhone.githubSync();
          if(q==="connected"){
            toast("GitHub connected — no token was entered.",5000);
            githubSection(box,after); return;
          }
          if(/^failed|^sync failed|^server error/.test(q)) throw new Error(q);
        }
        throw new Error("GitHub authorization timed out. Open Connect GitHub again.");
      } catch(e) {
        b.disabled=false; b.textContent="Connect GitHub";
        toast(e.message,9000);
      }
    };
  }
'''
s=s[:old_start]+new+s[old_end:]

old_start=s.index("  async function hubConnect(id, title) {")
old_end=s.index("  async function hubAction(action)", old_start)
new=r'''  async function hubConnect(id, title) {
    if (id !== "github") {
      toast(title + " is not connected yet. MusabAI will only mark a connector connected after real authentication.", 7000);
      return;
    }
    if (!(window.NewAlPhone && NewAlPhone.githubLogin && NewAlPhone.githubSync)) {
      toast("GitHub connection is available from the MusabAI Android app.",7000); return;
    }
    try {
      const started=NewAlPhone.githubLogin();
      if(started!=="started"){ toast(String(started),7000); return; }
      toast("GitHub opened. Approve access; MusabAI will finish automatically.",7000);
      for(let i=0;i<120;i++){
        await new Promise(r=>setTimeout(r,2000));
        const q=NewAlPhone.githubSync();
        if(q==="connected"){ toast("GitHub connected — no token was entered.",5000); await renderHub(); return; }
        if(/^failed|^sync failed|^server error/.test(q)){ toast(q,9000); return; }
      }
      toast("GitHub authorization timed out. Open Connect GitHub again.",9000);
    } catch(e){ toast(String(e),9000); }
  }
'''
s=s[:old_start]+new+s[old_end:]

# Cloud button must never call repository-backed cloud task submission.
s=s.replace('''    $("#open-cloud").onclick = () => openCloud();''',
            '''    $("#open-cloud").onclick = () => { localStorage.setItem("nc.pref.env","cloud"); updatePickers(); newThread(); $("#input").focus(); };''')

p.write_text(s,encoding="utf-8")
print("patched",p)
