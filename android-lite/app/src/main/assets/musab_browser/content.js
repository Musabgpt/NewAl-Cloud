/* MusabAI's page reader and hands, in the page the agent's hidden browser shows (top frame only). It connects to
   the app (HeadlessBrowser.java) and answers its commands:
   - snapshot: the page's address, title, visible text and its links, buttons and fields, numbered (the numbers stay
     on the elements as data-musab-n, for the next command);
   - click {n}, type {n, text, submit}, scroll {direction}: act on the page like a person would.
   Password values are never sent back. */
(() => {
  'use strict';
  const TEXT_LIMIT = 20000;
  const ITEM_LIMIT = 200;
  const SELECTOR = 'a[href], button, input:not([type="hidden"]), textarea, select, summary, ' +
    '[role="button"], [role="link"], [role="tab"], [role="menuitem"], [role="checkbox"], [role="option"], ' +
    '[contenteditable="true"], [contenteditable=""]';

  const clean = s => String(s || '').replace(/\s+/g, ' ').trim();

  function shown(el) {
    const st = getComputedStyle(el);
    if (st.visibility === 'hidden' || st.display === 'none' || st.opacity === '0') return false;
    if (!window.innerWidth || !window.innerHeight) return true;     // no layout size: trust the styles
    const r = el.getBoundingClientRect();
    return r.width >= 1 && r.height >= 1;
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
    const top = document.scrollingElement || document.documentElement;
    return {
      ok: true,
      url: location.href,
      title: document.title || '',
      text: text.slice(0, TEXT_LIMIT),
      truncated: text.length > TEXT_LIMIT,
      items,
      more_items: items.length >= ITEM_LIMIT,
      scroll: top ? {y: Math.round(top.scrollTop), height: Math.round(top.scrollHeight),
                     view: Math.round(window.innerHeight)} : null,
    };
  }

  function element(n) {
    const el = document.querySelector('[data-musab-n="' + Number(n) + '"]');
    if (!el) throw new Error('no item [' + n + '] on this page now: read the page again (browser_read)');
    return el;
  }

  function click(n) {
    const el = element(n);
    if (el.disabled) throw new Error('[' + n + '] is disabled');
    el.scrollIntoView({block: 'center'});
    if (typeof el.focus === 'function') el.focus();
    el.click();
    return 'clicked [' + n + '] ' + label(el);
  }

  function setValue(el, text) {
    const tag = el.tagName.toLowerCase();
    if (el.isContentEditable) {
      el.textContent = text;
    } else if (tag === 'select') {
      const want = clean(text).toLowerCase();
      const option = Array.from(el.options).find(o => o.value.toLowerCase() === want ||
        clean(o.text).toLowerCase() === want);
      if (!option) throw new Error('no option "' + text + '" in that list');
      el.value = option.value;
    } else {
      el.value = text;       // the element's own value setter (frameworks see the change on the events below)
    }
    el.dispatchEvent(new Event('input', {bubbles: true}));
    el.dispatchEvent(new Event('change', {bubbles: true}));
  }

  function enter(el) {
    for (const type of ['keydown', 'keypress', 'keyup']) {
      el.dispatchEvent(new KeyboardEvent(type, {key: 'Enter', code: 'Enter', keyCode: 13, which: 13, bubbles: true}));
    }
  }

  function type(n, text, submit) {
    const el = element(n);
    if (el.disabled || el.readOnly) throw new Error('[' + n + '] can not be typed into');
    if (kind(el) !== 'field') throw new Error('[' + n + '] is not a field: click it instead');
    el.scrollIntoView({block: 'center'});
    if (typeof el.focus === 'function') el.focus();
    setValue(el, String(text));
    if (submit) {
      const form = el.form;
      if (form && typeof form.requestSubmit === 'function') form.requestSubmit();
      else if (form) form.submit();
      else enter(el);
    }
    return 'typed into [' + n + '] ' + label(el) + (submit ? ' and submitted' : '');
  }

  function scroll(direction) {
    const step = Math.round((window.innerHeight || 800) * 0.85);
    if (direction === 'top') window.scrollTo(0, 0);
    else if (direction === 'bottom') window.scrollTo(0, (document.scrollingElement || document.documentElement).scrollHeight);
    else window.scrollBy(0, direction === 'up' ? -step : step);
    return 'scrolled ' + (direction || 'down');
  }

  let port;
  try {
    port = browser.runtime.connectNative('musab');
  } catch (e) {
    return;                                   // not MusabAI's browser
  }
  port.onMessage.addListener(msg => {
    if (!msg || msg.type !== 'command') return;
    let reply;
    try {
      if (msg.act === 'snapshot') reply = snapshot();
      else if (msg.act === 'click') reply = {ok: true, did: click(msg.n)};
      else if (msg.act === 'type') reply = {ok: true, did: type(msg.n, msg.text, msg.submit)};
      else if (msg.act === 'scroll') reply = {ok: true, did: scroll(msg.direction)};
      else reply = {ok: false, error: 'unknown command ' + msg.act};
    } catch (e) {
      reply = {ok: false, error: String(e && e.message || e)};
    }
    port.postMessage(Object.assign(reply, {type: 'reply', id: msg.id}));
  });
})();
