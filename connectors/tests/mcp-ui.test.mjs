import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {JSDOM} from 'jsdom';
const code = readFileSync(new URL('../mcp_ui.js', import.meta.url), 'utf8');
const tick = () => new Promise(resolve => setImmediate(resolve));
async function setup(t, fail = false) {
  const dom = new JSDOM('<html lang="ar"><div class="connector-panel"><div id="connector-list"></div></div></html>', {runScripts:'outside-only',url:'http://localhost/'});
  t.after(() => dom.window.close());
  const w = dom.window, calls = []; let sid = 'project';
  w.NewAlWorkspaceSession = () => sid;
  w.fetch = async (path, options) => {
    calls.push({path,body: options.body && JSON.parse(options.body)});
    const error = fail && options.method === 'POST';
    return {ok:!error,json:async () => error ? {error:'authentication required'} : path.endsWith('/save') ? {ok:true,tools:2} : {servers:[{name:'fixture',url:'https://example.com/mcp',tools:2}]}};
  };
  w.eval(code); await tick();
  w.document.querySelector('#mcp-name').value = 'fixture';
  w.document.querySelector('#mcp-url').value = 'https://example.com/mcp';
  w.document.querySelector('#mcp-token').value = 'private-token';
  return {w,calls,setSession:s => sid=s};
}
test('successful addition discovers tools and clears the password field', async t => {
  const {w,calls} = await setup(t);
  w.document.querySelector('form').dispatchEvent(new w.Event('submit',{cancelable:true})); await tick();
  assert.equal(calls[0].body.session,'project');
  assert.equal(calls[0].body.token,'private-token');
  assert.equal(w.document.querySelector('#mcp-token').value,'');
  assert.match(w.document.querySelector('[role="status"]').textContent,/2/);
  assert.equal(w.document.body.textContent.includes('private-token'),false);
});
test('failed authentication never shows a saved connection', async t => {
  const {w,calls} = await setup(t,true);
  w.document.querySelector('form').dispatchEvent(new w.Event('submit',{cancelable:true})); await tick();
  assert.equal(calls.length,1);
  assert.match(w.document.querySelector('[role="status"]').textContent,/authentication required/);
  assert.equal(w.document.querySelector('button[type="submit"]').disabled,false);
});
test('no project means no MCP connection request', async t => {
  const {w,calls,setSession} = await setup(t); setSession(null);
  w.document.querySelector('form').dispatchEvent(new w.Event('submit',{cancelable:true})); await tick();
  assert.equal(calls.length,0);
  assert.match(w.document.querySelector('[role="status"]').textContent,/مشروع/);
});
