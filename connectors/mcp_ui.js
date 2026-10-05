// Musab Hub MCP integrations: vetted local bundles + custom remote HTTP MCP.
(() => {
  'use strict';
  const tr = (en, ar) => document.documentElement.lang.startsWith('ar') ? ar : en;
  const node = (tag, text = '') => { const e = document.createElement(tag); e.textContent = text; return e; };
  const current = () => window.NewAlWorkspaceSession?.();

  async function api(path, body) {
    const r = await fetch(path, {
      method: body ? 'POST' : 'GET',
      credentials: 'same-origin',
      headers: body ? {'Content-Type': 'application/json'} : {},
      body: body ? JSON.stringify(body) : undefined
    });
    const data = await r.json();
    if (!r.ok || data.error) throw new Error(data.error || 'MCP request failed');
    return data;
  }

  function statusLabel(bundle) {
    if (bundle.status === 'enabled') return tr('Connected', 'متصل');
    if (bundle.status === 'available') return tr('Ready to enable', 'جاهز للتفعيل');
    if (bundle.status === 'credentials_missing') return tr('Credential required', 'يحتاج تسجيل/رمز وصول');
    if (bundle.status === 'runtime_missing') return tr('Runtime missing', 'بيئة التشغيل غير موجودة');
    return bundle.status || tr('Unavailable', 'غير متاح');
  }

  document.addEventListener('DOMContentLoaded', () => {
    const panel = document.querySelector('.connector-panel');
    if (!panel) return;

    // ---------------------------------------------------------------- Free AI provider credentials
    const providersSection = node('section');
    providersSection.className = 'connector-card free-providers';
    providersSection.append(node('h3', tr('Free AI providers', 'مزودو الذكاء المجانيون')));
    providersSection.append(node('p', tr(
      'Keys are stored in Android Keystore. MusabAI only uses the free pool: Groq → Gemini → OpenRouter Free → NVIDIA.',
      'تُحفظ المفاتيح داخل Android Keystore. يستخدم MusabAI المسار المجاني فقط: Groq ← Gemini ← OpenRouter Free ← NVIDIA.'
    )));
    const providerMessage = node('p');
    providerMessage.setAttribute('role', 'status');
    const providerList = node('div');
    const providerRefresh = node('button', tr('Refresh provider status', 'تحديث حالة المزودين'));
    providerRefresh.type = 'button'; providerRefresh.className = 'btn';
    providersSection.append(providerRefresh, providerMessage, providerList);
    panel.insertBefore(providersSection, document.querySelector('#connector-list'));

    let providerBusy = false;
    async function withProviderBusy(fn) {
      if (providerBusy) return;
      providerBusy = true; providerRefresh.disabled = true;
      try { await fn(); }
      catch (error) { providerMessage.textContent = error.message; }
      finally { providerBusy = false; providerRefresh.disabled = false; }
    }

    async function loadProviders() {
      const data = await api('/api/free-providers');
      providerList.replaceChildren();
      for (const provider of data.providers || []) {
        const row = node('section'); row.className = 'connector-card free-provider';
        row.append(node('strong', provider.name));
        row.append(node('p', provider.configured
          ? tr('Key saved securely', 'المفتاح محفوظ بأمان')
          : tr('Key not configured', 'المفتاح غير مضاف')));
        const input = node('input');
        input.type = 'password'; input.autocomplete = 'off';
        input.placeholder = tr('API key', 'مفتاح API');
        input.setAttribute('aria-label', provider.name + ' API key');
        const save = node('button', tr('Save key', 'حفظ المفتاح'));
        save.type = 'button'; save.className = 'btn primary';
        save.onclick = () => withProviderBusy(async () => {
          const key = input.value.trim();
          if (!key) throw new Error(tr('Paste an API key first.', 'ألصق مفتاح API أولًا.'));
          await api('/api/free-providers/save', {provider: provider.id, key});
          input.value = '';
          providerMessage.textContent = tr('Saved in Android Keystore.', 'تم الحفظ داخل Android Keystore.');
          await loadProviders();
        });
        row.append(input, save);
        if (provider.configured) {
          const test = node('button', tr('Test', 'اختبار'));
          test.type = 'button'; test.className = 'btn';
          test.onclick = () => withProviderBusy(async () => {
            providerMessage.textContent = tr('Testing the real free endpoint…', 'جارٍ اختبار الخدمة المجانية فعليًا…');
            await api('/api/free-providers/test', {provider: provider.id});
            providerMessage.textContent = tr('Connected to the free endpoint.', 'تم الاتصال بالخدمة المجانية.');
          });
          const remove = node('button', tr('Remove key', 'حذف المفتاح'));
          remove.type = 'button'; remove.className = 'btn';
          remove.onclick = () => withProviderBusy(async () => {
            await api('/api/free-providers/remove', {provider: provider.id});
            providerMessage.textContent = tr('Key removed.', 'تم حذف المفتاح.');
            await loadProviders();
          });
          row.append(test, remove);
        }
        providerList.append(row);
      }
    }
    providerRefresh.onclick = () => withProviderBusy(async () => { providerMessage.textContent = ''; await loadProviders(); });
    withProviderBusy(loadProviders);

    // ---------------------------------------------------------------- Official bundles
    const bundlesSection = node('section');
    bundlesSection.className = 'connector-card mcp-bundles';
    bundlesSection.append(node('h3', tr('MCP tools', 'أدوات MCP')));
    bundlesSection.append(node('p', tr(
      'Playwright, GitHub, Filesystem, Android and Memory are verified before they are marked connected. Missing runtimes stay disabled instead of showing a fake connection.',
      'يتم اختبار Playwright وGitHub والملفات وAndroid والذاكرة فعليًا قبل إظهارها كمتصلة. إذا كانت بيئة التشغيل ناقصة تبقى معطلة بدل اتصال وهمي.'
    )));
    const bundleMessage = node('p');
    bundleMessage.setAttribute('role', 'status');
    const bundleRefresh = node('button', tr('Refresh MCP status', 'تحديث حالة MCP'));
    bundleRefresh.type = 'button'; bundleRefresh.className = 'btn';
    const bundleList = node('div');
    bundlesSection.append(bundleRefresh, bundleMessage, bundleList);
    panel.insertBefore(bundlesSection, document.querySelector('#connector-list'));

    let bundleBusy = false;
    async function withBundleBusy(fn) {
      if (bundleBusy) return;
      bundleBusy = true; bundleRefresh.disabled = true;
      try { await fn(); }
      catch (error) { bundleMessage.textContent = error.message; }
      finally { bundleBusy = false; bundleRefresh.disabled = false; }
    }

    async function loadBundles() {
      const sid = current();
      const suffix = sid ? '?session=' + encodeURIComponent(sid) : '';
      const data = await api('/api/mcp-bundles' + suffix);
      bundleList.replaceChildren();
      for (const bundle of data.bundles || []) {
        const row = node('section'); row.className = 'connector-card mcp-bundle';
        row.append(node('strong', bundle.name));
        row.append(node('p', bundle.description || ''));
        const state = node('p', statusLabel(bundle));
        state.className = 'connector-status status-' + String(bundle.status || 'unknown');
        row.append(state);
        if (bundle.native_fallback) row.append(node('p', bundle.native_fallback));
        if (bundle.missing?.length) row.append(node('p', tr('Missing: ', 'الناقص: ') + bundle.missing.join(', ')));
        if (bundle.enabled) row.append(node('p', tr('Tools: ', 'الأدوات: ') + bundle.tools));

        const action = node('button');
        action.className = 'btn';
        action.type = 'button';
        if (bundle.enabled) {
          action.textContent = tr('Disable', 'تعطيل');
          action.onclick = () => withBundleBusy(async () => {
            if (!sid || current() !== sid) throw new Error(tr('Open a project conversation first.', 'افتح محادثة أو مشروعًا أولًا.'));
            await api('/api/mcp-bundles/disable', {session: sid, id: bundle.id});
            bundleMessage.textContent = tr('MCP disabled.', 'تم تعطيل MCP.');
            await loadBundles();
          });
        } else {
          action.textContent = bundle.available ? tr('Test and enable', 'اختبار وتفعيل') : tr('Unavailable', 'غير متاح');
          action.disabled = !bundle.available;
          action.onclick = () => withBundleBusy(async () => {
            if (!sid || current() !== sid) throw new Error(tr('Open a project conversation first.', 'افتح محادثة أو مشروعًا أولًا.'));
            bundleMessage.textContent = tr('Running a real MCP handshake…', 'جارٍ تنفيذ اختبار MCP فعلي…');
            const result = await api('/api/mcp-bundles/enable', {session: sid, id: bundle.id});
            bundleMessage.textContent = tr('Connected. Tools: ', 'تم الاتصال. الأدوات: ') + result.tools;
            await loadBundles();
          });
        }
        row.append(action);
        bundleList.append(row);
      }
    }
    bundleRefresh.onclick = () => withBundleBusy(async () => { bundleMessage.textContent = ''; await loadBundles(); });
    // Initial status is safe even without a project; activation still requires one.
    withBundleBusy(loadBundles);

    // ---------------------------------------------------------------- Custom remote HTTP MCP
    const section = node('section'); section.className = 'connector-card custom-mcp';
    const heading = node('h3', tr('Add MCP server', 'إضافة خادم MCP'));
    const intro = node('p', tr(
      'Remote Streamable HTTP. Tools become available in this project after a successful test. Browser OAuth services use the connection cards above.',
      'خادم بعيد ببروتوكول Streamable HTTP. تصبح أدواته متاحة في هذا المشروع بعد نجاح الاختبار. الخدمات التي تحتاج OAuth بالمتصفح تُربط من بطاقاتها بالأعلى.'
    ));
    const form = node('form'), message = node('p'), list = node('div');
    message.setAttribute('role', 'status');

    function field(label, type, id, placeholder) {
      const box = node('label', label), input = node('input');
      input.type = type; input.id = id; input.placeholder = placeholder; input.autocomplete = 'off';
      box.append(input); form.append(box); return input;
    }

    const name = field(tr('Name', 'الاسم'), 'text', 'mcp-name', 'my-server');
    name.required = true; name.maxLength = 24;
    const url = field(tr('MCP URL', 'رابط MCP'), 'url', 'mcp-url', 'https://example.com/mcp');
    url.required = true;
    const token = field(tr('Access token (optional)', 'رمز الوصول (اختياري)'), 'password', 'mcp-token', 'Bearer token');
    const submit = node('button', tr('Test and add', 'اختبار وإضافة'));
    submit.className = 'btn primary'; submit.type = 'submit'; form.append(submit);
    const refresh = node('button', tr('Show saved servers', 'عرض الخوادم المحفوظة'));
    refresh.type = 'button'; refresh.className = 'btn';
    section.append(heading, intro, form, message, refresh, list);
    panel.insertBefore(section, document.querySelector('#connector-list'));

    let busy = false;
    function requireSession(sid) {
      if (!sid || current() !== sid) throw new Error(tr('Open a project conversation first.', 'افتح محادثة أو مشروعًا أولًا.'));
    }

    async function load() {
      const sid = current(); requireSession(sid);
      const data = await api('/api/mcp-servers?session=' + encodeURIComponent(sid)); requireSession(sid);
      list.replaceChildren();
      const custom = (data.servers || []).filter(server => !server.bundle);
      if (!custom.length) list.append(node('p', tr('No custom MCP servers yet.', 'لا توجد خوادم MCP مضافة بعد.')));
      for (const server of custom) {
        const row = node('section'); row.className = 'connector-card';
        row.append(node('strong', server.name), node('p', server.url),
          node('p', tr('Last successful test: ', 'آخر اختبار ناجح: ') + server.tools + tr(' tools', ' أداة')));
        for (const op of ['test', 'remove']) {
          const button = node('button', op === 'test' ? tr('Test', 'اختبار') : tr('Remove', 'حذف'));
          button.className = 'btn';
          button.onclick = () => run(async () => {
            requireSession(sid);
            if (op === 'remove' && !window.confirm(tr('Remove this MCP server from the project?', 'حذف خادم MCP من هذا المشروع؟'))) return;
            const result = await api('/api/mcp-servers/' + op, {session: sid, name: server.name}); requireSession(sid);
            message.textContent = op === 'test'
              ? tr('Test passed. Tools: ', 'نجح الاختبار. الأدوات: ') + result.tools
              : tr('Removed.', 'تم الحذف.');
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
      try { await fn(); }
      catch (error) { message.textContent = error.message; }
      finally { busy = false; submit.disabled = refresh.disabled = false; }
    }

    form.onsubmit = event => {
      event.preventDefault();
      run(async () => {
        const sid = current(); requireSession(sid);
        const result = await api('/api/mcp-servers/save', {
          session: sid, name: name.value.trim(), url: url.value.trim(), token: token.value.trim()
        });
        token.value = ''; requireSession(sid);
        message.textContent = tr('Added and tested. Tools: ', 'تمت الإضافة والاختبار. الأدوات: ') + result.tools;
        await load();
      });
    };
    refresh.onclick = () => run(async () => { await load(); message.textContent = ''; });
  });
})();
