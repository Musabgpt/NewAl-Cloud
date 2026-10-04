(() => {
  'use strict';
  const ar = () => document.documentElement.lang.startsWith('ar');
  const tr = (en, arabic) => ar() ? arabic : en;
  const node = (tag, text = '', cls = '') => { const n = document.createElement(tag); n.textContent = text; n.className = cls; return n; };
  const session = () => window.NewAlWorkspaceSession?.() || '';
  async function api(path, body) {
    const r = await fetch(path, {method: body ? 'POST' : 'GET', credentials: 'same-origin', headers: body ? {'Content-Type': 'application/json'} : {}, body: body ? JSON.stringify(body) : undefined});
    const data = await r.json(); if (!r.ok || data.error) throw new Error(data.error || 'Request failed'); return data;
  }
  function dialog(title) {
    const outer = node('div', '', 'modal'); const card = node('div', '', 'modal-card connector-panel');
    const header = node('header'); header.append(node('span', title));
    const close = node('button', '×', 'icon-btn'); close.setAttribute('aria-label', tr('Close', 'إغلاق'));
    close.onclick = () => outer.remove(); header.append(close); card.append(header); outer.append(card);
    outer.setAttribute('role', 'dialog'); outer.setAttribute('aria-modal', 'true');
    outer.onclick = e => { if (e.target === outer) outer.remove(); };
    outer.onkeydown = e => {
      if (e.key === 'Escape') outer.remove();
      if (e.key === 'Tab') {
        const controls = [...card.querySelectorAll('button:not(:disabled),a,input,textarea')];
        const first = controls[0], last = controls.at(-1);
        if (e.shiftKey && document.activeElement === first) {e.preventDefault(); last.focus();}
        else if (!e.shiftKey && document.activeElement === last) {e.preventDefault(); first.focus();}
      }
    };
    document.body.append(outer); close.focus(); return card;
  }
  function prompt(text, path = '') {
    const input = document.querySelector('#input');
    input.value = text + (path ? '\n' + path : ''); input.dispatchEvent(new Event('input', {bubbles: true})); input.focus();
  }
  async function openFiles() {
    const card = dialog(tr('Files', 'الملفات')), info = node('p', tr('Create documents by asking in chat. Import, read and save files here.', 'اطلب إنشاء الملفات بالمحادثة. من هون بتقدر تستوردها وتقرأها وتحفظها.'));
    card.append(info); const message = node('p', '', 'muted'), bar = node('div', '', 'connector-actions'), list = node('div'); card.append(bar, message, list);
    const importButton = node('button', tr('Import a file', 'استيراد ملف'), 'btn primary');
    const input = node('input'); input.type = 'file'; input.accept = '.html,.md,.pdf,.zip,.txt'; input.hidden = true;
    const sid = session();
    const refresh = async () => {
      try {
        const data = await api('/api/documents?session=' + encodeURIComponent(sid)); list.replaceChildren();
        if (!data.files.length) list.append(node('p', tr('No documents yet.', 'ما في ملفات بعد.')));
        for (const file of data.files) {
          const row = node('section', '', 'connector-card'), details = node('div'); details.append(node('strong', file.path), node('small', `${file.format.toUpperCase()} · ${Math.ceil(file.bytes/1024)} KB`, 'muted'));
          const actions = node('div', '', 'connector-actions');
          const read = node('button', tr('Read', 'قراءة'), 'btn');
          read.onclick = async () => { try { const data = await api('/api/documents/read', {session: sid, path: file.path}); const view = dialog(file.name); const text = node('pre', data.text); text.style.cssText = 'white-space:pre-wrap;overflow-wrap:anywhere'; view.append(text); } catch(e) { message.textContent = e.message; } };
          const save = node('button', tr('Save', 'حفظ'), 'btn primary');
          const url = '/api/documents/download?' + new URLSearchParams({session: sid, path: file.path});
          save.onclick = () => {
            if (window.NewAlPhone?.saveDocument) NewAlPhone.saveDocument(new URL(url, location.href).href, file.name, ({pdf:'application/pdf',zip:'application/zip',html:'text/html',md:'text/markdown',txt:'text/plain'})[file.format]);
            else { const link = node('a'); link.href = url; link.download = file.name; document.body.append(link); link.click(); link.remove(); }
          };
          const use = node('button', tr('Work on it', 'اشتغل عليه'), 'btn'); use.onclick = () => {card.closest('.modal').remove(); prompt(tr('Read this file and help me improve it:', 'اقرأ هالملف وساعدني أحسّنه:'),file.path);};
          actions.append(read, save, use); row.append(details, actions); list.append(row);
        }
      } catch(e) { message.textContent = e.message; }
    };
    input.onchange = async () => {
      const file = input.files[0]; if (!file) return;
      if (file.size > 32*1024*1024) {message.textContent = tr('Maximum file size is 32 MB.', 'أقصى حجم للملف 32 ميغابايت.'); return;}
      importButton.disabled = true; message.textContent = tr('Importing…', 'جارٍ الاستيراد…');
      try {const data = await new Promise((resolve, reject) => {const reader = new FileReader(); reader.onload = () => resolve(reader.result.split(',')[1]); reader.onerror = reject; reader.readAsDataURL(file);}); await api('/api/documents/import',{session:sid,path:file.name,data}); message.textContent = tr('Imported.', 'تم الاستيراد.'); await refresh();}
      catch(e) {message.textContent = e.message;} finally {importButton.disabled = false; input.value = '';}
    };
    importButton.onclick = () => input.click(); bar.append(importButton, input);
    const create = node('button', tr('Create a document', 'إنشاء ملف'), 'btn'); create.onclick = () => {card.closest('.modal').remove(); prompt(tr('Create a document for me in ', 'أنشئ لي ملف بصيغة '));}; bar.append(create);
    await refresh();
  }
  async function openEvolution() {
    const card = dialog(tr('Improve the app', 'تطوير البرنامج')); const message = node('p', '', 'muted');
    card.append(node('p', tr('Describe one improvement. The agent prepares a separate engine copy, edits it and tests it. Activate a verified version here; return to the original whenever needed.', 'حدد تحسينًا واحدًا. البرنامج بيجهّز نسخة منفصلة من محرّكه ويعدّلها ويختبرها. من هون بتفعّل نسخة نجحت بالاختبار وبتقدر ترجع للأصل.')));
    const goal = node('textarea'); goal.placeholder = tr('What should improve?', 'شو بدك يتحسّن؟'); goal.style.width = '100%'; card.append(goal);
    const ask = node('button', tr('Prepare improvement', 'جهّز التحسين'), 'btn primary');
    ask.onclick = () => {if (!goal.value.trim()) return; card.closest('.modal').remove(); prompt(tr('Improve your Python engine for this goal. Use self_evolve, edit the isolated candidate, then self_evolve_verify. Report test evidence and do not activate it yourself. Goal: ', 'طوّر محرّكك لتحقيق هالهدف. استخدم self_evolve، عدّل النسخة المنفصلة، ثم self_evolve_verify. اعرض نتيجة الاختبارات وخلي التفعيل إلي. الهدف: ') + goal.value);};
    const rollback = node('button', tr('Restore original engine', 'رجوع للمحرّك الأصلي'), 'btn');
    rollback.onclick = async () => {try {const r = await api('/api/evolution/rollback', {}); message.textContent = tr(r.text, 'تم اختيار النسخة السابقة أو الأصلية. أعد تشغيل التطبيق.');}catch(e){message.textContent=e.message;}};
    card.append(ask, rollback, message);
    try {
      const data = await api('/api/evolution');
      for (const item of data.candidates) {
        const row = node('section', '', 'connector-card'); row.append(node('span', item.goal + ' · ' + item.status));
        if (item.status === 'verified') {const activate = node('button', tr('Activate', 'تفعيل'), 'btn primary'); activate.onclick = async () => {try {await api('/api/evolution/activate', {candidate:item.id}); message.textContent = tr('Restart the app to use this engine.', 'أعد تشغيل التطبيق لاستخدام هالنسخة.');}catch(e){message.textContent=e.message;}}; row.append(activate);}
        card.append(row);
      }
    }catch(e){message.textContent=e.message;}
  }
  document.addEventListener('DOMContentLoaded', () => {
    for (const [label, arabic, action] of [['Files','الملفات',openFiles],['Improve the app','تطوير البرنامج',openEvolution]]) {
      const b = node('button', tr(label,arabic),'side-item'); b.onclick=action; document.querySelector('.side-top').append(b);
    }
  });
})();
