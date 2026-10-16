/* MusabAI's page reader, in the page shown in the browser pane (top frame only). It connects to the app
   (BrowserPane.java) and, when asked, answers with the page: its address, title, visible text and its links, buttons
   and fields, numbered. The numbers stay on the elements (data-musab-n) for the next phase's clicks and typing.
   It reads; it changes nothing on the page but those numbers. Password values are never sent. */
(() => {
  'use strict';
  const TEXT_LIMIT = 20000;
  const ITEM_LIMIT = 200;
  const SELECTOR = 'a[href], button, input:not([type="hidden"]), textarea, select, summary, ' +
    '[role="button"], [role="link"], [role="tab"], [role="menuitem"], [role="checkbox"], [contenteditable="true"], ' +
    '[contenteditable=""]';

  const clean = s => String(s || '').replace(/\s+/g, ' ').trim();

  function shown(el) {
    const r = el.getBoundingClientRect();
    if (r.width < 1 || r.height < 1) return false;
    const st = getComputedStyle(el);
    return st.visibility !== 'hidden' && st.display !== 'none' && st.opacity !== '0';
  }

  function kind(el) {
    const tag = el.tagName.toLowerCase();
    if (tag === 'a' || el.getAttribute('role') === 'link') return 'link';
    if (tag === 'input') {
      const type = (el.type || 'text').toLowerCase();
      if (['button', 'submit', 'reset', 'image'].includes(type)) return 'button';
      if (type === 'checkbox' || type === 'radio') return type;
      return 'field';
    }
    if (tag === 'textarea' || tag === 'select' || el.isContentEditable) return 'field';
    if (el.getAttribute('role') === 'checkbox') return 'checkbox';
    return 'button';
  }

  function label(el) {
    const tag = el.tagName.toLowerCase();
    const type = (el.type || '').toLowerCase();
    let text = el.getAttribute('aria-label') || '';
    if (!text && el.labels && el.labels.length) text = el.labels[0].innerText;
    if (!text && (tag === 'input' && ['button', 'submit', 'reset'].includes(type))) text = el.value;
    if (!text && tag !== 'input' && tag !== 'textarea' && tag !== 'select') text = el.innerText;
    if (!text) text = el.getAttribute('placeholder') || el.getAttribute('title') || el.getAttribute('alt') ||
      el.getAttribute('name') || '';
    if (!text && tag === 'a') {
      const img = el.querySelector('img[alt]');
      if (img) text = img.getAttribute('alt');
    }
    return clean(text).slice(0, 100);
  }

  function snapshot() {
    document.querySelectorAll('[data-musab-n]').forEach(el => el.removeAttribute('data-musab-n'));
    const items = [];
    for (const el of document.querySelectorAll(SELECTOR)) {
      if (items.length >= ITEM_LIMIT) break;
      if (!shown(el)) continue;
      const n = items.length + 1;
      el.setAttribute('data-musab-n', String(n));
      const item = {n, kind: kind(el), label: label(el)};
      const tag = el.tagName.toLowerCase();
      if (tag === 'a' && el.href) item.href = el.href;
      if (tag === 'input') item.type = (el.type || 'text').toLowerCase();
      if (item.kind === 'field' && item.type !== 'password' && 'value' in el && el.value) {
        item.value = clean(el.value).slice(0, 100);
      }
      if (item.kind === 'checkbox' || item.kind === 'radio') item.checked = Boolean(el.checked);
      if (el.disabled) item.disabled = true;
      items.push(item);
    }
    const body = document.body ? document.body.innerText : '';
    const text = String(body || '').replace(/[ \t]+\n/g, '\n').replace(/\n{3,}/g, '\n\n').trim();
    return {
      url: location.href,
      title: document.title || '',
      text: text.slice(0, TEXT_LIMIT),
      truncated: text.length > TEXT_LIMIT,
      items,
      more_items: items.length >= ITEM_LIMIT,
    };
  }

  let port;
  try {
    port = browser.runtime.connectNative('musab');
  } catch (e) {
    return;                                   // not MusabAI's browser
  }
  port.onMessage.addListener(msg => {
    if (!msg || msg.type !== 'snapshot') return;
    let page;
    try {
      page = snapshot();
    } catch (e) {
      page = {url: location.href, title: document.title || '', text: '', items: [], error: String(e)};
    }
    port.postMessage(Object.assign({type: 'snapshot', id: msg.id}, page));
  });
})();
