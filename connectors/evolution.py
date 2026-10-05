"""Isolated Python-engine candidates with evidence-bound activation and rollback."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import secrets
from . import settings, tools

NAMES = ['self_evolve', 'self_evolve_verify', 'memory_learn']

def home():
    p=Path(settings.HOME)/'evolution'; p.mkdir(parents=True,exist_ok=True); return p

def save(path, data):
    tmp=path.with_suffix('.tmp'); tmp.write_text(json.dumps(data,ensure_ascii=False),encoding='utf-8'); os.replace(tmp,path)

def digest(path):
    if path.is_symlink(): raise tools.ToolError('Engine candidates cannot contain symbolic links')
    h=hashlib.sha256()
    for f in sorted(path.rglob('*')):
        if f.is_symlink(): raise tools.ToolError('Engine candidates cannot contain symbolic links')
        if f.is_file() and '__pycache__' not in f.parts and '.git' not in f.parts:
            h.update(f.relative_to(path).as_posix().encode()); h.update(f.read_bytes())
    return h.hexdigest()

def candidate(cid):
    if not isinstance(cid,str) or len(cid)!=24 or any(c not in '0123456789abcdef' for c in cid): raise tools.ToolError('Invalid candidate ID')
    p=home()/'candidates'/cid
    if p.is_symlink() or not p.is_dir() or p.resolve().parent != (home()/'candidates').resolve(): raise tools.ToolError('Candidate does not exist')
    for child in p.iterdir():
        if child.name not in ('newal_code', 'test-home') or child.is_symlink() or not child.is_dir():
            raise tools.ToolError('Keep candidate code inside newal_code and check outputs inside test-home')
    return p

@tools.tool('self_evolve', 'Prepare an isolated copy of this Python engine for improvement. Edit its files using normal tools, then call self_evolve_verify. Does not modify the running engine or Android APK.', {'goal':tools._s('specific improvement goal'), 'checks':{'type':'array','items':{'type':'string'},'description':'additional test commands for verification'}}, ['goal'], 'exec')
def prepare(ctx, goal, checks=None):
    cid=secrets.token_hex(12); p=home()/'candidates'/cid; p.mkdir(parents=True)
    source=Path(__file__).resolve().parent
    shutil.copytree(source,p/'newal_code',ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
    if ctx.session is not None and str(p) not in ctx.session.dirs: ctx.session.dirs.append(str(p))
    record={'id':cid,'goal':str(goal)[:2000],'created':time.time(),'status':'prepared','source_digest':digest(p/'newal_code'),'checks':checks or [],'packaged_build':os.environ.get('NEWAL_PACKAGED_BUILD','host')}
    save(home()/(cid+'.json'),record)
    return json.dumps(dict(record,path=str(p),instruction='Edit newal_code in this candidate, then run self_evolve_verify. The user can activate a verified candidate from the app.'),ensure_ascii=False), {'candidate':cid,'path':str(p)}

@tools.tool('self_evolve_verify', 'Verify an edited self-improvement candidate with syntax, isolated imports and the packaged document/evolution/addon/memory regression tests, plus requested checks. These are local checks, not an OS security sandbox or a guarantee of intelligence. Activation requires a changed candidate with all checks passing.', {'candidate':tools._s('candidate ID')}, ['candidate'], 'exec')
def verify(ctx, candidate):
    p=globals()['candidate'](candidate); file=home()/(candidate+'.json'); record=json.loads(file.read_text())
    before=digest(p/'newal_code')
    if before==record['source_digest']: raise tools.ToolError('No engine changes yet; edit the candidate before verification')
    env=dict(os.environ); env['PYTHONPATH']=str(p)+os.pathsep+str(Path(__file__).resolve().parent.parent)
    env['PYTHONDONTWRITEBYTECODE']='1'; env['NEWAL_CODE_HOME']=str(p/'test-home')
    env['NEWAL_MEMORY_HOME']=str(p/'test-home'/'memory')
    # Test code comes from the installed package, not the edited candidate. Imports
    # inside those tests still resolve against the candidate under verification.
    trusted=Path(os.environ['NEWAL_PACKAGED_ENGINE'])/'newal_code' if os.environ.get('NEWAL_PACKAGED_ENGINE') else Path(__file__).resolve().parent
    runner='''import importlib.util, pathlib, sys, unittest
base = pathlib.Path(%r)
suite = unittest.TestSuite()
for name in ('document_tests', 'evolution_tests', 'addon_tests', 'memory_tests', 'autonomy_tests', 'prompt_tests', 'workbench_tests', 'mcp_config_tests'):
    spec = importlib.util.spec_from_file_location('newal_code._baseline_' + name, base / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    suite.addTests(unittest.defaultTestLoader.loadTestsFromModule(module))
result = unittest.TextTestRunner(verbosity=1).run(suite)
sys.exit(0 if result.wasSuccessful() and result.testsRun else 1)
''' % str(trusted)
    commands=[ [sys.executable,'-m','compileall','-q',str(p/'newal_code')],
              [sys.executable,'-c','from newal_code import documents,evolution,server,agent; assert documents.NAMES; print("engine imports passed")'],
              [sys.executable,'-c',runner] ]
    results=[]
    for command in commands+list(record.get('checks') or []):
        try:
            proc=subprocess.run(command,cwd=p,env=env,shell=isinstance(command,str),capture_output=True,text=True,timeout=120)
            results.append({'command':command,'exit':proc.returncode,'output':(proc.stdout+proc.stderr)[-8000:]})
        except subprocess.TimeoutExpired:
            results.append({'command':command,'exit':124,'output':'Verification timed out'})
        if results[-1]['exit']: break
    after=digest(p/'newal_code')
    ok=all(x['exit']==0 for x in results) and before==after
    record.update(status='verified' if ok else 'failed',verified_digest=after,results=results,verified_at=time.time())
    save(file,record)
    return json.dumps(record,ensure_ascii=False),record

@tools.tool('memory_learn', 'Remember a useful user preference or verified lesson with supporting evidence, for later tasks.', {'topic':tools._s('short topic'), 'lesson':tools._s('preference or lesson'), 'evidence':tools._s('why this lesson is supported')}, ['topic','lesson','evidence'], 'edit')
def learn(ctx, topic, lesson, evidence):
    from .autonomy import memory_for
    store=memory_for(ctx.root)
    try: learned=store.learn(topic,lesson,evidence)
    finally: store.close()
    if learned is None: return 'Memory is disabled or the lesson is empty; nothing saved.', {'memory':False}
    return 'Remembered lesson: '+str(topic), {'memory':True,'id':learned}

def status():
    records=[]
    for file in sorted(home().glob('*.json')):
        if file.name=='active.json': continue
        try: records.append(json.loads(file.read_text()))
        except (ValueError,OSError): continue
    active=home()/'active.json'
    return {'candidates':sorted(records,key=lambda x:x.get('created',0),reverse=True)[:30], 'active':json.loads(active.read_text()) if active.exists() else {}}

def activate(cid):
    p=candidate(cid); record=json.loads((home()/(cid+'.json')).read_text())
    if record.get('status')!='verified' or digest(p/'newal_code')!=record.get('verified_digest'): raise tools.ToolError('Candidate must pass verification again after its last edit')
    if record.get('packaged_build')!=os.environ.get('NEWAL_PACKAGED_BUILD','host'): raise tools.ToolError('This candidate belongs to a different app build; prepare and verify a new one')
    marker=home()/'active.json'; previous=json.loads(marker.read_text()) if marker.exists() else {}
    save(marker,{'id':cid,'path':str(p),'previous':previous.get('path',''),'activated':time.time(),'packaged_build':record['packaged_build']})
    return {'ok':True,'restart_required':True,'text':'Saved. Restart the engine to use the verified candidate.'}

def rollback():
    marker=home()/'active.json'
    if marker.exists():
        marker.unlink()
    return {'ok':True,'restart_required':True,'text':'Original packaged engine selected. Restart the engine.'}

def route(handler, method, path, body=None):
    if not path.startswith('/api/evolution'): return False
    try:
        if method=='GET' and path=='/api/evolution': handler._json(status())
        elif method=='POST' and path=='/api/evolution/activate': handler._json(activate((body or {}).get('candidate','')))
        elif method=='POST' and path=='/api/evolution/rollback': handler._json(rollback())
        else: handler._json({'error':'Not found'},404)
    except Exception as e: handler._json({'error':str(e)},400)
    return True
