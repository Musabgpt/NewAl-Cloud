(() => {
  'use strict';
  if (!window.NewAlPhone?.restartEngine) return;
  let pending = false, restarting = '', timer;
  async function check() {
    if (pending || restarting) return;
    pending = true;
    try {
      const response = await fetch('/api/evolution/automatic', {credentials: 'same-origin'});
      if (!response.ok) return;
      const state = await response.json();
      if (state.restart_ready === true && state.state === 'activating' && typeof state.candidate === 'string') {
        restarting = state.candidate;
        try { window.NewAlPhone.restartEngine(); }
        catch (error) { restarting = ''; console.error('Automatic engine restart failed', error); }
      }
    } catch (error) {
      // A restarting/temporarily offline engine is retried on the next poll.
      console.debug('Automatic update status unavailable', error);
    } finally { pending = false; }
  }
  window.addEventListener('focus', check);
  document.addEventListener('visibilitychange', () => { if (!document.hidden) check(); });
  timer = window.setInterval(check, 5000);
  window.addEventListener('pagehide', () => window.clearInterval(timer), {once: true});
  check();
})();
