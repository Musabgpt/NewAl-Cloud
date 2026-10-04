import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { JSDOM } from 'jsdom';
const code = readFileSync(new URL('../ui.js', import.meta.url), 'utf8');
const tick = () => new Promise(resolve => setImmediate(resolve));
async function panel(t, item) {
  const dom = new JSDOM('<html lang="ar"><div class="side-top"></div><button id="open-github"></button></html>', {runScripts: 'outside-only', url: 'http://localhost/'});
  t.after(() => dom.window.close());
  const w = dom.window;
  const state = {item, calls: []};
  w.fetch = async (url, options) => {
    state.calls.push(url);
    if (options.method === 'POST') return {ok: true, json: async () => ({ok: true})};
    return {ok: true, json: async () => ({connectors: [state.item]})};
  };
  w.eval(code);
  await tick();
  w.openMusabConnectors();
  await tick();
  state.dom = w.document;
  state.refresh = async () => { w.dispatchEvent(new w.Event('focus')); await tick(); };
  return state;
}
test('unchanged refresh preserves focused button and scrolled content', async t => {
  const state = await panel(t, {id: 'github', name: 'GitHub', configured: true, status: 'disconnected'});
  const button = state.dom.querySelector('[data-action="connect:github"]');
  button.focus();
  state.dom.querySelector('.connector-panel').scrollTop = 180;
  await state.refresh();
  assert.equal(state.dom.querySelector('[data-action="connect:github"]'), button);
  assert.equal(state.dom.activeElement, button);
  assert.equal(state.dom.querySelector('.connector-panel').scrollTop, 180);
});
test('failed browser flow offers reconnect without an unusable account test', async t => {
  const state = await panel(t, {id: 'github', name: 'GitHub', configured: true, status: 'error', has_credentials: false});
  assert.equal(state.dom.querySelector('[data-action="connect:github"]').disabled, false);
  assert.equal(state.dom.querySelector('[data-action="test:github"]'), null);
});
test('unchanged response after an action restores enabled controls', async t => {
  const state = await panel(t, {id: 'github', name: 'GitHub', configured: true, status: 'error', has_credentials: false});
  state.dom.querySelector('[data-action="disconnect:github"]').click();
  await tick();
  assert(state.calls.includes('/api/connectors/disconnect'));
  assert.equal(state.dom.querySelector('[data-action="connect:github"]').disabled, false);
  assert.equal(state.dom.querySelector('[data-action="disconnect:github"]').disabled, false);
});
test('unconfigured provider has an Arabic explanation and disabled connect', async t => {
  const state = await panel(t, {id: 'gmail', name: 'Gmail', configured: false, status: 'not_configured', error: 'OAuth application deployment required'});
  assert.equal(state.dom.querySelector('[data-action="connect:gmail"]').disabled, true);
  assert(state.dom.querySelector('#connector-list').textContent.includes('صاحب التطبيق'));
  assert(!state.dom.querySelector('#connector-list').textContent.includes('OAuth application deployment required'));
});
