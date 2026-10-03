from pathlib import Path
p=Path("desktop/newal_code/ui/app.js")
s=p.read_text(encoding="utf-8")
# Replace connector catalog with explicit transport metadata; no service is called connected unless backend proves it.
a=s.index("  const HUB_CONNECTORS = [")
b=s.index("  const HUB_APPS = [", a)
new='''  const HUB_CONNECTORS = [
    ["github","GitHub","Repos, issues, commits, PRs","oauth","https://api.githubcopilot.com/mcp/"],
    ["google-drive","Google Drive","Files, folders and documents","oauth","https://drivemcp.googleapis.com/mcp/v1"],
    ["gmail","Gmail","Search, read and send mail","oauth","https://gmailmcp.googleapis.com/mcp/v1"],
    ["google-calendar","Google Calendar","Events and scheduling","oauth","https://calendarmcp.googleapis.com/mcp/v1"],
    ["google-docs","Google Docs","Documents and content","oauth","https://docsmcp.googleapis.com/mcp/v1"],
    ["google-sheets","Google Sheets","Spreadsheets and data","oauth","https://sheetsmcp.googleapis.com/mcp/v1"],
    ["figma","Figma","Files, designs and comments","oauth","https://mcp.figma.com/mcp"],
    ["notion","Notion","Pages and databases","oauth","https://mcp.notion.com/mcp"],
    ["linear","Linear","Issues and projects","oauth",""],
    ["sentry","Sentry","Errors and releases","oauth",""],
    ["gitlab","GitLab","Repositories and merge requests","oauth",""],
    ["slack","Slack","Channels and messages","oauth",""],
    ["discord","Discord","Servers and messages","oauth",""],
    ["dropbox","Dropbox","Files and folders","oauth",""],
    ["onedrive","OneDrive","Files and folders","oauth",""],
    ["outlook","Microsoft Outlook","Mail and calendar","oauth",""],
    ["teams","Microsoft Teams","Chats and teams","oauth",""],
    ["trello","Trello","Boards and cards","oauth",""],
    ["jira","Jira","Issues and projects","oauth",""],
    ["asana","Asana","Tasks and projects","oauth",""],
    ["replit","Replit","Projects and deployments","oauth",""],
    ["kaggle","Kaggle","Datasets, notebooks and models","oauth",""],
    ["hugging-face","Hugging Face","Models and datasets","oauth",""],
    ["vercel","Vercel","Projects and deployments","oauth",""],
    ["netlify","Netlify","Sites and deployments","oauth",""],
    ["firebase","Firebase","Projects and services","oauth",""],
    ["supabase","Supabase","Projects, DB and edge functions","oauth"]
  ];
'''
s=s[:a]+new+s[b:]
# Replace hubConnect with generic connector start; native GitHub remains supported by Android bridge.
a=s.index("  async function hubConnect(id, title) {")
b=s.index("  async function hubAction(action)",a)
new='''  async function hubConnect(id, title) {
    const meta = HUB_CONNECTORS.find(x => x[0] === id);
    if (!meta) return;
    try {
      if (id === "github" && window.NewAlPhone && NewAlPhone.githubLogin) {
        const r=NewAlPhone.githubLogin();
        if(r!=="started") throw new Error(String(r));
        toast("GitHub opened. Approve access; MusabAI will finish automatically.",7000);
        for(let i=0;i<120;i++){
          await new Promise(r=>setTimeout(r,2000));
          const q=NewAlPhone.githubSync();
          if(q==="connected"){ toast("GitHub connected — no token was entered.",5000); await renderHub(); return; }
          if(/^failed|^sync failed|^server error/.test(q)) throw new Error(q);
        }
        throw new Error("Authorization timed out.");
      }
      const d=await api("/api/connectors/start",{id, title, mcp_url:meta[4]||""});
      if(d.connected){ toast(title+" connected.",5000); await renderHub(); return; }
      if(d.url && NewAlPhone && NewAlPhone.openUrl){
        NewAlPhone.openUrl(d.url);
        toast("Authorize "+title+" in the browser. MusabAI will detect the connection automatically.",7000);
        for(let i=0;i<120;i++){
          await new Promise(r=>setTimeout(r,2000));
          const q=await api("/api/connectors/status?id="+encodeURIComponent(id));
          if(q.connected){toast(title+" connected.",5000);await renderHub();return;}
        }
      }
      throw new Error(d.message || "This connector needs its official OAuth/MCP setup before it can be connected.");
    } catch(e){ toast(String(e.message||e),9000); }
  }
'''
s=s[:a]+new+s[b:]
# Connector cards should include real status/setup state.
old='''      const connected=!!(states[a[0]]&&states[a[0]].connected);
      const b=h("button","hub-card-item"+(connected?" connected":""),'<span class="hub-icon">'+(connected?"✓":"↗")+'</span><span><b>'+esc(a[1])+'</b><small>'+esc(a[2])+(connected?" · Connected":" · Connect")+'</small></span>');'''
new='''      const st=states[a[0]]||{};
      const connected=!!st.connected;
      const available=!!st.available;
      const b=h("button","hub-card-item"+(connected?" connected":""),'<span class="hub-icon">'+(connected?"✓":"↗")+'</span><span><b>'+esc(a[1])+'</b><small>'+esc(a[2])+(connected?" · Connected":available?" · Connect":" · Setup required")+'</small></span>');'''
s=s.replace(old,new)
# Make launcher section explicitly non-connector.
s=s.replace('<h3>Apps & services</h3>','<h3>Phone shortcuts — not agent connectors</h3><p class="hub-note">These buttons only open an Android app or website. They do not grant MusabAI access to your account.</p>')
p.write_text(s,encoding="utf-8")
