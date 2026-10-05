import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {JSDOM} from 'jsdom';

const code = readFileSync(new URL('../mcp_ui.js', import.meta.url), 'utf8');
const tick = () => new Promise(resolve => setImmediate(resolve));

async function setup(t, fail = false) {
  const dom = new JSDOM(
    '<html lang="ar"><div class="connector-panel"><div id="connector-list"></div></div></html>',
    {runScripts:'outside-only',url:'http://localhost/'}
  );
  t.after(() => dom.window.close());
  const w = dom.window, calls = []; let sid = 'project';
  w.NewAlWorkspaceSession = () => sid;
  w.fetch = async (path, options = {}) => {
    const body = options.body && JSON.parse(options.body);
    calls.push({path, method: options.method || 'GET', body});
    const error = fail && options.method === 'POST';
    if (error) return {ok:false,json:async () => ({error:'authentication required'})};
    if (String(path).startsWith('/api/free-providers')) {
      if (options.method === 'POST') return {ok:true,json:async () => (
        String(path).endsWith('/test') ? {ok:true,connected:true} : {ok:true,configured:true}
      )};
      return {ok:true,json:async () => ({free_only:true,providers:[
        {id:'groq',name:'Groq Free',configured:false},
        {id:'nvidia',name:'NVIDIA Free',configured:true}
      ]})};
    }
    if (String(path).startsWith('/api/mcp-bundles')) {
      if (options.method === 'POST') return {ok:true,json:async () => ({ok:true,tools:7,enabled:true})};
      return {ok:true,json:async () => ({bundles:[
        {id:'playwright',name:'Microsoft Playwright MCP',description:'Browser automation',status:'available',available:true,enabled:false,missing:[]},
        {id:'github',name:'GitHub MCP Server',description:'GitHub tools',status:'runtime_missing',available:false,enabled:false,missing:['github-mcp-server']}
      ]})};
    }
    if (String(path).endsWith('/save')) return {ok:true,json:async () => ({ok:true,tools:2})};
    return {ok:true,json:async () => ({servers:[{name:'fixture',url:'https://example.com/mcp',tools:2,bundle:''}]})};
  };
  w.eval(code); await tick();
  w.document.querySelector('#mcp-name').value = 'fixture';
  w.document.querySelector('#mcp-url').value = 'https://example.com/mcp';
  w.document.querySelector('#mcp-token').value = 'private-token';
  return {w,calls,setSession:s => sid=s};
}

test('successful custom addition discovers tools and clears the password field', async t => {
  const {w,calls} = await setup(t);
  w.document.querySelector('form').dispatchEvent(new w.Event('submit',{cancelable:true})); await tick();
  const request = calls.find(c => c.path === '/api/mcp-servers/save');
  assert.equal(request.body.session,'project');
  assert.equal(request.body.token,'private-token');
  assert.equal(w.document.querySelector('#mcp-token').value,'');
  assert.equal(w.document.body.textContent.includes('private-token'),false);
});

test('failed authentication never shows a saved custom connection', async t => {
  const {w,calls} = await setup(t,true);
  const before = calls.length;
  w.document.querySelector('form').dispatchEvent(new w.Event('submit',{cancelable:true})); await tick();
  assert.equal(calls.length,before+1);
  assert.match(w.document.querySelector('.custom-mcp [role="status"]').textContent,/authentication required/);
  assert.equal(w.document.querySelector('button[type="submit"]').disabled,false);
});

test('no project means no custom MCP connection request', async t => {
  const {w,calls,setSession} = await setup(t); setSession(null);
  const before = calls.filter(c => c.path === '/api/mcp-servers/save').length;
  w.document.querySelector('form').dispatchEvent(new w.Event('submit',{cancelable:true})); await tick();
  assert.equal(calls.filter(c => c.path === '/api/mcp-servers/save').length,before);
  assert.match(w.document.querySelector('.custom-mcp [role="status"]').textContent,/مشروع/);
});

test('official bundle is only enabled after a real backend activation response', async t => {
  const {w,calls} = await setup(t);
  const buttons = [...w.document.querySelectorAll('.mcp-bundle button')];
  const enable = buttons.find(b => b.textContent.includes('تفعيل'));
  assert(enable);
  enable.click(); await tick(); await tick();
  const request = calls.find(c => c.path === '/api/mcp-bundles/enable');
  assert.equal(request.body.session,'project');
  assert.equal(request.body.id,'playwright');
  assert.match(w.document.querySelector('.mcp-bundles [role="status"]').textContent,/7/);
});

test('missing runtime stays disabled instead of pretending connected', async t => {
  const {w} = await setup(t);
  const github = [...w.document.querySelectorAll('.mcp-bundle')].find(x => x.textContent.includes('GitHub MCP'));
  assert(github);
  const button = github.querySelector('button');
  assert.equal(button.disabled,true);
  assert(github.textContent.includes('غير متاح'));
});

test('free provider key is cleared after save and never rendered back into the page', async t => {
  const {w,calls} = await setup(t);
  const row = [...w.document.querySelectorAll('.free-provider')].find(x => x.textContent.includes('Groq'));
  assert(row);
  const input = row.querySelector('input[type="password"]');
  input.value = 'groq-secret-example';
  const save = [...row.querySelectorAll('button')].find(b => b.textContent.includes('حفظ'));
  save.click(); await tick(); await tick();
  const request = calls.find(c => c.path === '/api/free-providers/save');
  assert.equal(request.body.provider, 'groq');
  assert.equal(request.body.key, 'groq-secret-example');
  assert.equal(input.value, '');
  assert.equal(w.document.body.textContent.includes('groq-secret-example'), false);
});
