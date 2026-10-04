import PROVIDERS from './providers.json' with { type: 'json' };
const enc = new TextEncoder();
const b64 = a => btoa(String.fromCharCode(...new Uint8Array(a))).replaceAll('+','-').replaceAll('/','_').replace(/=+$/,'');
const un64 = s => Uint8Array.from(atob(s.replaceAll('-','+').replaceAll('_','/')), c=>c.charCodeAt(0));
const random = (n=32) => b64(crypto.getRandomValues(new Uint8Array(n)));
export const challenge = async value => b64(await crypto.subtle.digest('SHA-256',enc.encode(value)));
const equal = (a,b) => { if(typeof a!=='string'||typeof b!=='string'||a.length!==b.length)return false;let x=0;for(let i=0;i<a.length;i++)x|=a.charCodeAt(i)^b.charCodeAt(i);return x===0; };
export class BrokerError extends Error {}
async function limitedText(body, limit=65536) {
 if(!body)return '';const reader=body.getReader();let size=0,parts=[];
 while(true){const {done,value}=await reader.read();if(done)break;size+=value.length;if(size>limit){await reader.cancel();fail();}parts.push(value);}
 const all=new Uint8Array(size);let off=0;for(const part of parts){all.set(part,off);off+=part.length;}return new TextDecoder().decode(all);
}
const fail = () => {throw new BrokerError('Connection request failed; check app registration or reconnect');};
export function catalog(env) { return Object.fromEntries(Object.entries(PROVIDERS).map(([id,[p]])=>[id,!!(env[p+'_CLIENT_ID']&&env[p+'_CLIENT_SECRET'])])); }
async function key(env) {if(!env.MUSAB_GRANT_KEY||un64(env.MUSAB_GRANT_KEY).length!==32)fail();return crypto.subtle.importKey('raw',un64(env.MUSAB_GRANT_KEY),'AES-GCM',false,['encrypt','decrypt']);}
async function seal(env,id,data) {const iv=crypto.getRandomValues(new Uint8Array(12));const blob=await crypto.subtle.encrypt({name:'AES-GCM',iv,additionalData:enc.encode(id)},await key(env),enc.encode(JSON.stringify(data)));return JSON.stringify({iv:b64(iv),data:b64(blob)});}
async function open(env,id,raw) {const b=JSON.parse(raw);const clear=await crypto.subtle.decrypt({name:'AES-GCM',iv:un64(b.iv),additionalData:enc.encode(id)},await key(env),un64(b.data));return JSON.parse(new TextDecoder().decode(clear));}
function store(env) {if(!env.BUCKET)fail();return env.BUCKET;}
async function read(env,id) {if(!/^[A-Za-z0-9_-]{43}$/.test(id))fail();const obj=await store(env).get('oauth/'+id);if(!obj)fail();const rec=await open(env,id,await obj.text());if(rec.expires<=Date.now())fail();return {obj,rec};}
async function write(env,id,rec,etag) {const options={customMetadata:{expires:String(rec.expires)}};if(etag)options.onlyIf={etagMatches:etag};const result=await store(env).put('oauth/'+id,await seal(env,id,rec),options);if(!result)fail();return result;}
export async function start(env,provider,proof) {
 if(!catalog(env)[provider]||!/^https:\/\/[^/]+$/.test(env.MUSAB_PUBLIC_URL)||typeof proof!=='string'||!/^[-_A-Za-z0-9]{43}$/.test(proof))fail();
 const bucket=store(env);const list=await bucket.list({prefix:'oauth/',limit:1000,include:['customMetadata']});
 // Expired grants are unusable even before physical cleanup. Bound stored sessions.
 const expired=list.objects.filter(o=>Number(o.customMetadata?.expires||0)<=Date.now());
 if(expired.length)await bucket.delete(expired.slice(0,100).map(o=>o.key));
 if(list.truncated||list.objects.length-expired.length>=900)throw new BrokerError('Connection server is busy; try later');
 const [prefix,authorize,,scope]=PROVIDERS[provider],id=random(),verifier=random(48),redirect=env.MUSAB_PUBLIC_URL+'/oauth/callback/'+provider;
 await write(env,id,{provider,proof,verifier,redirect,expires:Date.now()+600000,status:'pending'});
 const q=new URLSearchParams({client_id:env[prefix+'_CLIENT_ID'],redirect_uri:redirect,response_type:'code',state:id});if(scope)q.set('scope',scope);
 if(provider!=='notion'){q.set('code_challenge',await challenge(verifier));q.set('code_challenge_method','S256');}
 if(prefix==='GOOGLE'){q.set('access_type','offline');q.set('prompt','consent');}if(provider==='notion')q.set('owner','user');
 return {id,authorization_url:authorize+'?'+q,expires_in:600};
}
export async function exchange(env,provider,fields,fetcher=fetch) {
 if(!catalog(env)[provider])fail();const [prefix,,url]=PROVIDERS[provider];let data,headers={Accept:'application/json'};
 if(provider==='notion'){headers.Authorization='Basic '+btoa(env[prefix+'_CLIENT_ID']+':'+env[prefix+'_CLIENT_SECRET']);headers['Content-Type']='application/json';headers['Notion-Version']='2022-06-28';data=JSON.stringify(fields);}
 else {headers['Content-Type']='application/x-www-form-urlencoded';data=new URLSearchParams({...fields,client_id:env[prefix+'_CLIENT_ID'],client_secret:env[prefix+'_CLIENT_SECRET']}).toString();}
 const res=await fetcher(url,{method:'POST',headers,body:data,redirect:'error',signal:AbortSignal.timeout(30000)});if(!res.ok)fail();
 const reader=res.body.getReader();let size=0,chunks=[];while(true){const {done,value}=await reader.read();if(done)break;size+=value.length;if(size>65536){await reader.cancel();fail();}chunks.push(value);}
 const all=new Uint8Array(size);let off=0;for(const c of chunks){all.set(c,off);off+=c.length;}const tokens=JSON.parse(new TextDecoder().decode(all));if(tokens.error||!tokens.access_token)fail();
 return Object.fromEntries(['access_token','refresh_token','expires_in','refresh_token_expires_in','scope','token_type'].filter(k=>k in tokens).map(k=>[k,tokens[k]]));
}
export async function callback(env,provider,q,fetcher=fetch) {
 const id=q.state;const {rec,obj}=await read(env,id);if(rec.provider!==provider||rec.status!=='pending')fail();
 rec.status='exchanging';const locked=await write(env,id,rec,obj.etag);
 try {if(q.error||!q.code)fail();const fields={grant_type:'authorization_code',code:q.code,redirect_uri:rec.redirect};if(provider!=='notion')fields.code_verifier=rec.verifier;rec.tokens=await exchange(env,provider,fields,fetcher);rec.status='ready';}
 catch {rec.status='failed';rec.error='Authorization did not complete';}delete rec.verifier;await write(env,id,rec,locked.etag);if(rec.status==='failed')fail();
}
export async function poll(env,id,verifier) {
 if(typeof verifier!=='string'||!/^[-_A-Za-z0-9]{43,128}$/.test(verifier))fail();const {rec,obj}=await read(env,id);if(!equal(rec.proof,await challenge(verifier)))fail();
 if(rec.status==='consumed')fail();if(!['ready','failed'].includes(rec.status))return {status:'pending'};
 const result=rec.status==='ready'?{status:'ready',tokens:rec.tokens}:{status:'failed',error:rec.error};
 // CAS ensures only one poller receives tokens. Keep only a short-lived tombstone.
 await write(env,id,{provider:rec.provider,proof:rec.proof,expires:rec.expires,status:'consumed'},obj.etag);return result;
}
const html = ok => `<!doctype html><html lang="ar" dir="rtl"><meta name="viewport" content="width=device-width"><title>MusabAI</title><body style="font:18px system-ui;background:#10141d;color:#eee;padding:40px"><h1>${ok?'وصل التفويض':'لم يكتمل التفويض'}</h1><p>ارجع إلى MusabAI ${ok?'ليختبر الاتصال.':'وأعد المحاولة.'}</p><a style="color:#90d8b0" href="musabai://connectors">العودة للتطبيق</a></body></html>`;
export async function handle(req,env,fetcher=fetch) {
 const u=new URL(req.url);let result,status=200,isHtml=false;
 try {
  if(req.method==='GET'&&u.pathname==='/v1/catalog')result={providers:catalog(env)};
  else if(req.method==='GET'&&u.pathname==='/v1/health')result={ok:true,storage:!!env.BUCKET,configured:Object.values(catalog(env)).filter(Boolean).length};
  else if(req.method==='GET'&&/^\/oauth\/callback\/[a-z]+$/.test(u.pathname)){isHtml=true;await callback(env,u.pathname.split('/').pop(),Object.fromEntries(u.searchParams),fetcher);result=html(true);}
  else if(req.method==='POST'&&['/v1/start','/v1/poll','/v1/refresh'].includes(u.pathname)){
   const body=await limitedText(req.body);const b=JSON.parse(body);if(!b||Array.isArray(b)||typeof b!=='object')fail();
   if(u.pathname==='/v1/start')result=await start(env,b.provider,b.challenge);
   if(u.pathname==='/v1/poll')result=await poll(env,b.id,b.verifier);
   if(u.pathname==='/v1/refresh'){if(typeof b.refresh_token!=='string'||!b.refresh_token)fail();result=await exchange(env,b.provider,{grant_type:'refresh_token',refresh_token:b.refresh_token},fetcher);}
  }else {status=404;result={error:'Not found'};}
 }catch {status=400;result=isHtml?html(false):{error:'Connection request failed; check app registration or reconnect'};}
 return new Response(isHtml?result:JSON.stringify(result),{status,headers:{'Content-Type':isHtml?'text/html; charset=utf-8':'application/json','Cache-Control':'no-store','Referrer-Policy':'no-referrer','X-Content-Type-Options':'nosniff','Content-Security-Policy':"default-src 'none'; style-src 'unsafe-inline'"}});
}
