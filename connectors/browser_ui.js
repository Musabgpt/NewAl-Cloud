/* The in-app browser's button in the chat's top bar (a globe, before the terminal button): it shows or hides the
   browser pane above the conversation (BrowserPane.java). The agent's browser_open shows the pane by itself.
   Only in the Android app (window.NewAlPhone): the app takes the newal://browser/toggle link (MainActivity). */
(() => {
  'use strict';
  if (!window.NewAlPhone) return;
  const ar = () => (document.documentElement.lang || navigator.language || '').startsWith('ar');
  const GLOBE = '<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" ' +
    'stroke-width="1.8" stroke-linecap="round" aria-hidden="true"><circle cx="12" cy="12" r="9"/>' +
    '<path d="M3 12h18M12 3c2.5 2.7 3.8 5.7 3.8 9s-1.3 6.3-3.8 9c-2.5-2.7-3.8-5.7-3.8-9S9.5 5.7 12 3z"/></svg>';

  function add() {
    if (document.getElementById('toggle-browser')) return;
    const before = document.getElementById('toggle-terminal');
    if (!before || !before.parentNode) return;
    const b = document.createElement('button');
    b.id = 'toggle-browser';
    b.type = 'button';
    b.className = 'icon-btn';
    b.title = ar() ? 'المتصفح' : 'Browser';
    b.setAttribute('aria-label', b.title);
    b.innerHTML = GLOBE;
    b.addEventListener('click', () => { window.location.href = 'newal://browser/toggle'; });
    before.parentNode.insertBefore(b, before);
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', add);
  else add();
})();
