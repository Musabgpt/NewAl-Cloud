// Custom remote MCP connections, scoped to the current project.
(() => {
  'use strict';
  const tr = (en, ar) => document.documentElement.lang.startsWith('ar') ? ar : en;
  const node = (tag, text = '') => { const e = document.createElement(tag); e.textContent = text; return e; };
  const current = () => window.NewAlWorkspaceSession?.();
  async function api(path, body) {
    const r = await fetch(path, {method: body ? 'POST' : 'GET', credentials: 'same-origin',
      headers: body ? {'Content-Type': 'application/json'} : {}, body: body ? JSON.stringify(body) : undefined});
    const data = await r.json();
    if (!r.ok || data.error) throw new Error(data.error || 'MCP request failed');
    return data;
  }
  document.addEventListener('DOMContentLoaded', () => {
    const card = document.querySelector('.connector-panel'); if (!card) return;
    const section = node('section'); section.className = 'connector-card custom-mcp';
    const heading = node('h3', tr('Add MCP server', 'إضافة خادم MCP'));
    const intro = node('p', tr('Remote Streamable HTTP. Tools become available in this project after a successful test. Browser OAuth services use the connection cards above.', 'خادم بعيد ببروتوكول Streamable HTTP. تصبح أدواته متاحة في هذا المشروع بعد نجاح الاختبار. الخدمات التي تحتاج OAuth بالمتصفح تُربط من بطاقاتها بالأعلى.'));
    const form = node('form'), message = node('p'), list = node('div');
    message.setAttribute('role', 'status');
    function field(label, type, id, placeholder) {
      const box = node('label', label), input = node('input'); input.type = type; input.id = id;
      input.placeholder = placeholder; input.autocomplete = 'off'; box.append(input); form.append(box); return input;
    }
    const name = field(tr('Name', 'الاسم'), 'text', 'mcp-name', 'my-server'); name.required = true; name.maxLength = 24;
    const url = field(tr('MCP URL', 'رابط MCP'), 'url', 'mcp-url', 'https://example.com/mcp'); url.required = true;
    const token = field(tr('Access token (optional)', 'رمز الوصول (اختياري)'), 'password', 'mcp-token', 'Bearer token');
    const submit = node('button', tr('Test and add', 'اختبار وإضافة')); submit.className = 'btn primary'; submit.type = 'submit'; form.append(submit);
    const refresh = node('button', tr('Show saved servers', 'عرض الخوادم المحفوظة')); refresh.type = 'button'; refresh.className = 'btn';
    section.append(heading, intro, form, message, refresh, list); card.insertBefore(section, document.querySelector('#connector-list'));
    let busy = false;
    function requireSession(sid) {
      if (!sid || current() !== sid) throw new Error(tr('Open a project conversation first.', 'افتح محادثة أو مشروعًا أولًا.'));
    }
    async function load() {
      const sid = current(); requireSession(sid);
      const data = await api('/api/mcp-servers?session=' + encodeURIComponent(sid)); requireSession(sid);
      list.replaceChildren();
      if (!data.servers.length) list.append(node('p', tr('No custom MCP servers yet.', 'لا توجد خوادم MCP مضافة بعد.')));
      for (const server of data.servers) {
        const row = node('section'); row.className = 'connector-card';
        row.append(node('strong', server.name), node('p', server.url), node('p', tr('Last successful test: ', 'آخر اختبار ناجح: ') + server.tools + tr(' tools', ' أداة')));
        for (const op of ['test', 'remove']) {
          const button = node('button', op === 'test' ? tr('Test', 'اختبار') : tr('Remove', 'حذف')); button.className = 'btn';
          button.onclick = () => run(async () => {
            requireSession(sid);
            if (op === 'remove' && !window.confirm(tr('Remove this MCP server from the project?', 'حذف خادم MCP من هذا المشروع؟'))) return;
            const result = await api('/api/mcp-servers/' + op, {session: sid, name: server.name}); requireSession(sid);
            message.textContent = op === 'test' ? tr('Test passed. Tools: ', 'نجح الاختبار. الأدوات: ') + result.tools : tr('Removed.', 'تم الحذف.');
            await load();
          });
          row.append(button);
        }
        list.append(row);
      }
    }
    async function run(fn) {
      if (busy) return; busy = true; submit.disabled = refresh.disabled = true;
      message.textContent = tr('Testing connection…', 'جارٍ اختبار الاتصال…');
      try { await fn(); } catch (error) { message.textContent = error.message; }
      finally { busy = false; submit.disabled = refresh.disabled = false; }
    }
    form.onsubmit = event => {
      event.preventDefault();
      run(async () => {
        const sid = current(); requireSession(sid);
        const result = await api('/api/mcp-servers/save', {session: sid, name: name.value.trim(), url: url.value.trim(), token: token.value.trim()});
        token.value = ''; requireSession(sid);
        message.textContent = tr('Added and tested. Tools: ', 'تمت الإضافة والاختبار. الأدوات: ') + result.tools;
        await load();
      });
    };
    refresh.onclick = () => run(async () => { await load(); message.textContent = ''; });
  });
})();
