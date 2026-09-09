"""Integration tests against tools/service.ps1 start; no existing external setup is used."""
import asyncio
import concurrent.futures
import json
import time
import uuid
from pathlib import Path
import httpx
import psutil
import pytest
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client
from service.client import Client
from service.config import read_config

EVIDENCE = Path('.local/validation')
EVIDENCE.mkdir(exist_ok=True)
SMALL, LARGE = '/small.exe', '/large.exe'


@pytest.fixture
def client():
    c = Client()
    s = c.call('session_open', label='integration')['session']
    records = []
    def run(op, args=None, success=True, timeout=120):
        r = c.run(s, op, args or {}, timeout)
        records.append(r)
        if success:
            assert r['status'] == 'completed', r
        return r
    def identity(p=SMALL):
        return next(x for x in run('programs')['output']['loaded'] if x['id'] == p)
    yield c, s, run, identity
    (EVIDENCE / f'{uuid.uuid4().hex}.json').write_text(json.dumps(records, indent=2))
    c.call('session_close', session=s)


def test_real_parallel_decompilation(client):
    c, s, run, identity = client
    functions = ['work_000', 'work_001', 'work_002', 'work_003']
    baseline = {f: run('decompile', {'program': LARGE, 'function': f, 'cache': False, 'coalesce': False})['output']['code'] for f in functions}
    sessions = [c.call('session_open')['session'] for _ in functions]
    try:
        def task(pair):
            sid, f = pair
            return Client().run(sid, 'decompile', {'program': LARGE, 'function': f, 'cache': False, 'coalesce': False})
        with concurrent.futures.ThreadPoolExecutor(4) as pool:
            results = list(pool.map(task, zip(sessions, functions)))
        for r, f in zip(results, functions):
            assert r['status'] == 'completed', r
            assert r['output']['code'] == baseline[f]
        outputs = [r['output'] for r in results]
        assert len({o['program_instance'] for o in outputs}) == 1
        overlaps = [(a, b) for a in outputs for b in outputs
                    if a['worker'] != b['worker'] and max(a['native_start_ns'], b['native_start_ns']) < min(a['native_end_ns'], b['native_end_ns'])]
        assert overlaps, outputs
        (EVIDENCE / 'overlap.json').write_text(json.dumps(results, indent=2))
    finally:
        for sid in sessions:
            c.call('session_close', session=sid)


def test_two_official_sdk_clients():
    config = read_config()
    async def task(function):
        async with streamablehttp_client(f"http://127.0.0.1:{config['port']}/mcp", headers={'Authorization':'Bearer '+config['token']}) as streams:
            async with ClientSession(streams[0], streams[1]) as session:
                await session.initialize()
                async def call(name, args):
                    result = await session.call_tool(name, args)
                    assert not result.isError, result
                    return result.structuredContent or json.loads(result.content[0].text)
                sid = (await call('session_open', {}))['session']
                try:
                    jid = (await call('job_submit', {'session':sid,'operation':'decompile','arguments':{'program':LARGE,'function':function,'cache':False,'coalesce':False}}))['id']
                    while True:
                        r = await call('job_result', {'session':sid,'job':jid})
                        if r['status'] in ('completed','failed','cancelled','timed_out'):
                            assert r['status'] == 'completed', r
                            return r
                        await asyncio.sleep(.02)
                finally:
                    await call('session_close', {'session':sid})
    async def both():
        return await asyncio.gather(task('work_010'), task('work_011'))
    records = asyncio.run(both())
    assert len({r['output']['program_instance'] for r in records}) == 1
    (EVIDENCE/'sdk-clients.json').write_text(json.dumps(records, indent=2))


def test_atomic_rollback_conflict_and_persistence(client):
    c,s,run,identity = client
    original = run('decompile', {'program':SMALL,'function':'mix'})
    v = identity()['version']
    failed = run('edit', {'program':SMALL,'expected_version':v,'changes':[
        {'op':'rename_function','function':'mix','name':'should_rollback'},
        {'op':'variable_type','function':'should_rollback','variable':'param_1','type':'does_not_exist'}]}, False)
    assert failed['effect'] == 'rolled_back'
    assert failed['program']['version'] == v
    assert run('decompile', {'program':SMALL,'function':'mix'})['output']['code'] == original['output']['code']
    changed = run('edit', {'program':SMALL,'expected_version':v,'save':False,'changes':[
        {'op':'comment','address':'140001064','type':'PRE','text':'volatile-test'}]})
    assert not changed['program']['durable']
    stale = run('edit', {'program':SMALL,'expected_version':v,'changes':[{'op':'namespace','name':'stale_namespace'}]}, False)
    assert 'stale_revision' in stale['error']
    assert 'volatile-test' in run('decompile', {'program':SMALL,'function':'mix'})['output']['code']
    saved = run('program_save', {'program':SMALL,'expected_version':identity()['version']})
    assert saved['program']['durable']
    run('program_close', {'program':SMALL,'expected_version':identity()['version']})
    run('program_open', {'path':SMALL})
    assert 'volatile-test' in run('decompile', {'program':SMALL,'function':'mix'})['output']['code']
    run('edit', {'program':SMALL,'expected_version':identity()['version'],'changes':[{'op':'comment','address':'140001064','type':'PRE','text':''}]})


def test_edits_and_type_effects(client):
    c,s,run,identity = client
    def edit(changes):
        return run('edit', {'program':SMALL,'expected_version':identity()['version'],'changes':changes})
    edit([{'op':'define_type','declaration':'typedef struct Entry { unsigned int key; unsigned int value; } Entry;'},
          {'op':'prototype','function':'sum_records','signature':'unsigned int sum_records(Entry *records, unsigned int count);'}])
    code = run('decompile', {'program':SMALL,'function':'sum_records'})['output']['code']
    assert 'Entry' in code and 'records' in code and 'key' in code, code
    variables = run('decompile', {'program':SMALL,'function':'mix'})['output']['variables']
    param = next(x['name'] for x in variables if x['name'].startswith('param_'))
    edit([{'op':'rename_variable','function':'mix','variable':param,'name':'input_value'}])
    assert 'input_value' in run('decompile', {'program':SMALL,'function':'mix'})['output']['code']
    edit([{'op':'variable_type','function':'mix','variable':'input_value','type':'int'}])
    assert 'int input_value' in run('decompile', {'program':SMALL,'function':'mix'})['output']['code']
    edit([{'op':'rename_variable','function':'mix','variable':'input_value','name':param},
          {'op':'variable_type','function':'mix','variable':param,'type':'uint'}])
    data = run('query', {'program':SMALL,'kind':'symbols','filter':'counter'})['output']['items'][0]['address']
    edit([{'op':'rename_data','address':data,'name':'counter_named'},
          {'op':'apply_type','address':data,'type':'int','clear':True},
          {'op':'namespace','name':'fixture_'+uuid.uuid4().hex[:8]}])
    assert run('query', {'program':SMALL,'kind':'data','filter':'counter_named'})['output']['items']
    edit([{'op':'rename_data','address':data,'name':'counter'}])


def test_scripts_analysis_and_export(client):
    c,s,run,identity = client
    for name, expected in [('ContextProbe.java','nested=shared-with-nested'),('jython_probe.py','jython-program=small.exe'),('PromptProbe.java','prompt=property-value')]:
        result = run('script', {'program':SMALL,'expected_version':identity()['version'],'name':name,
                               'paths':['tests/fixtures/scripts'],'address':'140001064','selection':[['140001064','140001067']]})
        assert expected in result['output']['stdout'], result
    failed = run('script', {'program':SMALL,'expected_version':identity()['version'],'name':'FailAfterEdit.java',
                            'paths':['tests/fixtures/scripts'],'address':'140001064'},False)
    assert failed['effect'] == 'partially_applied'
    assert 'before-failure' in failed['output']['stderr']
    run('analyze', {'program':SMALL,'expected_version':identity()['version'],'all':False})
    result = run('export', {'program':SMALL,'expected_version':identity()['version'],'format':'GzfExporter',
                            'file':f'.local/exports/{uuid.uuid4().hex}.gzf'})
    assert result['output']['size'] > 0


def test_queued_and_running_cancellation(client):
    c,s,run,identity = client
    def submit(op,args,timeout=120):
        return c.call('job_submit',session=s,operation=op,arguments=args,timeout_seconds=timeout)['id']
    first = submit('script',{'program':SMALL,'expected_version':identity()['version'],'name':'Cooperative.java','args':['5000'],'paths':['tests/fixtures/scripts']})
    deadline=time.monotonic()+10
    while c.call('job_status',session=s,job=first)['status'] != 'running':
        assert time.monotonic()<deadline
        time.sleep(.02)
    queued = submit('decompile',{'program':LARGE,'function':'work_100','cache':False})
    c.call('job_cancel',session=s,job=queued)
    assert c.wait(s,queued)['status']=='cancelled'
    c.call('job_cancel',session=s,job=first)
    assert c.wait(s,first)['status']=='cancelled'
    assert run('decompile',{'program':LARGE,'function':'work_101','cache':False})['status']=='completed'
    timeout = submit('script',{'program':SMALL,'expected_version':identity()['version'],'name':'Cooperative.java','args':['5000'],'paths':['tests/fixtures/scripts']},.1)
    assert c.wait(s,timeout)['status']=='timed_out'


def test_native_worker_failure_recovers(client):
    c,s,run,identity = client
    run('decompile', {'program':LARGE,'function':'work_120','cache':False})
    health=c.call('service_health')
    children=[x for x in health['owned_processes'] if x['name'].lower()=='decompile.exe']
    assert children
    process=psutil.Process(children[0]['pid'])
    assert process.ppid()==health['engine_pid']
    process.kill()
    for name in ('work_121','work_122','work_123'):
        run('decompile', {'program':LARGE,'function':name,'cache':False})
    assert c.call('service_health')['generation']==health['generation']


def test_auth_origin_and_host():
    cfg=read_config()
    url=f"http://127.0.0.1:{cfg['port']}/mcp"
    data={'jsonrpc':'2.0','id':1,'method':'tools/list'}
    with httpx.Client() as client:
        assert client.post(url,json=data).status_code==403
        headers={'Authorization':'Bearer '+cfg['token'],'Origin':'http://untrusted.example'}
        assert client.post(url,json=data,headers=headers).status_code==403
        headers.pop('Origin');headers['Host']='untrusted.example'
        assert client.post(url,json=data,headers=headers).status_code==403


def test_session_isolation(client):
    c,s,run,identity=client
    other=c.call('session_open')['session']
    job=run('programs')['id']
    try:
        with pytest.raises(RuntimeError):
            c.call('job_result',session=other,job=job)
    finally:
        c.call('session_close',session=other)


def test_writer_progress_and_read_barrier(client):
    c,s,run,identity=client
    v=identity(LARGE)['version']
    def submit(op,args):
        return c.call('job_submit',session=s,operation=op,arguments=args)['id']
    earlier=[submit('decompile',{'program':LARGE,'function':f'work_{i:03d}','cache':False,'coalesce':False}) for i in (180,181)]
    writer=submit('edit',{'program':LARGE,'expected_version':v,'changes':[{'op':'comment','address':'140001000','text':'writer progress'}]})
    later=[submit('decompile',{'program':LARGE,'function':f'work_{i:03d}','cache':False,'coalesce':False}) for i in range(182,188)]
    before=[c.wait(s,j) for j in earlier]
    changed=c.wait(s,writer)
    after=[c.wait(s,j) for j in later]
    assert changed['status']=='completed',changed
    assert all(r['backend_end_ns']<=changed['backend_start_ns'] for r in before)
    assert all(r['backend_start_ns']>=changed['backend_end_ns'] for r in after)
    assert all(r['program']['version']==changed['program']['version'] for r in after)
    (EVIDENCE/'writer-barrier.json').write_text(json.dumps(before+[changed]+after,indent=2))


def test_queue_bound_and_timeout(client):
    c,s,run,identity=client
    # Warm script compilation before measuring the reservation.
    run('script',{'program':SMALL,'expected_version':identity()['version'],'name':'Cooperative.java','args':['1'],'paths':['tests/fixtures/scripts']})
    blocker=c.call('job_submit',session=s,operation='script',arguments={'program':SMALL,'expected_version':identity()['version'],
        'name':'Cooperative.java','args':['15000'],'paths':['tests/fixtures/scripts']})['id']
    sessions=[c.call('session_open')['session'] for _ in range(6)]
    accepted=[]
    try:
        rejected=False
        for i in range(80):
            sid=sessions[i%6]
            try:
                job=c.call('job_submit',session=sid,operation='decompile',arguments={'program':LARGE,'function':'work_150'})['id']
                accepted.append((sid,job))
            except RuntimeError as ex:
                assert 'queue_full' in str(ex),ex
                rejected=True
                break
        assert rejected
        assert c.call('service_health')['queued']<=read_config()['queue_limit']
        for sid,job in accepted:
            c.call('job_cancel',session=sid,job=job)
        assert all(c.call('job_status',session=sid,job=job)['status']=='cancelled' for sid,job in accepted)
    finally:
        c.call('job_cancel',session=s,job=blocker)
        c.wait(s,blocker)
        for sid in sessions:c.call('session_close',session=sid)


def test_batch_cache_and_coalescing(client):
    c,s,run,identity=client
    args={'program':LARGE,'function':'work_200','cache':True}
    first=run('decompile',args)
    second=run('decompile',args)
    assert second['output']['cache_hit']
    assert first['output']['code']==second['output']['code']
    batch=run('decompile_batch',{'program':LARGE,'functions':['work_200','work_201'],'cache':False})
    assert batch['output'][0]['code']==first['output']['code']
    assert len(batch['output'])==2


def test_import_lifecycle_and_function_creation(client):
    c,s,run,identity=client
    run('program_close',{'program':LARGE,'expected_version':identity(LARGE)['version']})
    name='fresh_'+uuid.uuid4().hex[:8]
    try:
        imported=run('program_import',{'file':'.local/fixtures/small.exe','name':name,'analyze':False,
            'loader':'PeLoader','language':'x86:LE:64:default','compiler':'windows','loader_options':{'-loader-loadLibraries':'false'},
            'paths':['tests/fixtures/scripts'],'pre_scripts':[{'name':'Continuation.java','args':['CONTINUE','imports']}],
            'post_scripts':[{'name':'LifecyclePost.java'}]})
        p=imported['output']['id']
        assert p=='/imports/'+name
        assert 'mode=import' in imported['output']['script']['stdout']
        v=imported['program']['version']
        r=run('edit',{'program':p,'expected_version':v,'changes':[
            {'op':'disassemble','address':'140001064','length':40},
            {'op':'create_function','address':'140001064','name':'created_mix'}]})
        assert 'created_mix' in run('decompile',{'program':p,'function':'140001064'})['output']['code']
        deleted=run('script',{'program':p,'expected_version':r['program']['version'],'allow_delete':True,
            'name':'Continuation.java','args':['ABORT_AND_DELETE'],'paths':['tests/fixtures/scripts']})
        assert deleted['effect']=='deleted'
        discarded=run('program_import',{'file':'.local/fixtures/small.exe','name':name,'paths':['tests/fixtures/scripts'],
            'pre_scripts':[{'name':'Continuation.java','args':['ABORT_AND_DELETE']}]})
        assert discarded['output']['discarded']
        assert not any(name in x for x in run('programs')['output']['files'])
    finally:
        for t in run('programs')['output']['loaded']:
            if t['id'] not in (SMALL,LARGE):run('program_close',{'program':t['id'],'expected_version':t['version']})
        run('program_open',{'path':LARGE})


def test_jython_failure_and_cancel(client):
    c,s,run,identity=client
    failed=run('script',{'program':SMALL,'expected_version':identity()['version'],'paths':['tests/fixtures/scripts'],'name':'jython_failure.py'},False)
    assert failed['status']=='failed' and 'python fixture failure' in failed['error']
    assert 'before-python-failure' in failed['output']['stdout']
    timeout=run('script',{'program':SMALL,'expected_version':identity()['version'],'paths':['tests/fixtures/scripts'],'name':'jython_cancel.py'},False,3)
    assert timeout['status']=='timed_out',timeout


def test_compiled_java_script(client):
    c,s,run,identity=client
    r=run('script',{'program':SMALL,'expected_version':identity()['version'],'paths':['.local/fixture-classes'],
                    'name':'NestedPlain.class','args':['compiled-class']})
    assert 'plain-nested=compiled-class' in r['output']['stdout']


def test_running_read_cancel_isolated(client):
    c,s,run,identity=client
    other=c.call('session_open')['session']
    try:
        first=c.call('job_submit',session=s,operation='decompile_batch',arguments={'program':LARGE,
            'functions':[f'work_{i:03d}' for i in range(64)],'cache':False,'coalesce':False})['id']
        second=c.call('job_submit',session=other,operation='decompile_batch',arguments={'program':LARGE,
            'functions':[f'work_{i:03d}' for i in range(64,72)],'cache':False,'coalesce':False})['id']
        time.sleep(.1)
        assert c.call('job_status',session=s,job=first)['status']=='running'
        c.call('job_cancel',session=s,job=first)
        assert c.wait(s,first)['status']=='cancelled'
        assert c.wait(other,second)['status']=='completed'
    finally:c.call('session_close',session=other)


def test_analysis_options_and_path_containment(client):
    c,s,run,identity=client
    result=run('analyze',{'program':SMALL,'expected_version':identity()['version'],'all':False,
        'analysis_options':{'ASCII Strings':True,'ASCII Strings.Minimum String Length':'LEN_5'}})
    assert result['output']['analysis_complete']
    failed=run('export',{'program':SMALL,'expected_version':identity()['version'],'file':'../outside-test.gzf'},False)
    assert 'within checkout' in failed['error']
    # Read-only query bounds must fail before returning an unbounded result.
    failed=run('query',{'program':SMALL,'kind':'functions','offset':1000001},False)
    assert 'Offset limit' in failed['error']


def test_analysis_stage_timeout_lifecycle(client):
    c,s,run,identity=client
    result=run('script',{'program':SMALL,'expected_version':identity()['version'],'paths':['tests/fixtures/scripts'],
        'pre_scripts':[{'name':'SlowAnalyzer.java'}],'post_scripts':[{'name':'LifecyclePost.java'}],
        'analyze':True,'all':False,'analysis_timeout':1})
    assert result['output']['analysis_timed_out']
    assert 'post-analysis-timeout=true' in result['output']['stdout']


def test_cancelled_atomic_batch_rolls_back(client):
    c,s,run,identity=client
    before=run('decompile',{'program':SMALL,'function':'mix'})
    variable=next(v['name'] for v in before['output']['variables'] if v['name'].startswith('param_'))
    changes=[{'op':'rename_function','function':'mix','name':'cancelled_rename'}]
    changes += [{'op':'variable_type','function':'cancelled_rename','variable':variable,'type':'int'} for _ in range(24)]
    job=c.call('job_submit',session=s,operation='edit',arguments={'program':SMALL,'expected_version':before['program']['version'],'changes':changes})['id']
    time.sleep(.2)
    assert c.call('job_status',session=s,job=job)['status']=='running'
    c.call('job_cancel',session=s,job=job)
    result=c.wait(s,job)
    assert result['status']=='cancelled' and result['effect']=='rolled_back',result
    assert result['program']['version']==before['program']['version']
    assert run('decompile',{'program':SMALL,'function':'mix'})['output']['code']==before['output']['code']


@pytest.mark.parametrize('script',['ExitEngine.java','Uncooperative.java'])
def test_engine_recovery_no_replay(client,script):
    c,s,run,identity=client
    before=c.call('service_health')
    # A volatile edit must disappear after recovery.
    run('edit',{'program':SMALL,'expected_version':identity()['version'],'save':False,'changes':[
        {'op':'comment','address':'140001064','type':'PRE','text':'must disappear on crash'}]})
    job=c.call('job_submit',session=s,operation='script',arguments={
        'program':SMALL,'expected_version':identity()['version'],'name':script,'paths':['tests/fixtures/scripts']},timeout_seconds=5)['id']
    result=c.wait(s,job,45)
    assert result['status'] in ('failed','timed_out'), result
    assert result['effect']=='outcome_unknown', result
    deadline=time.monotonic()+90
    while True:
        health=c.call('service_health')
        if health['state']=='ready' and health['generation']!=before['generation']:
            break
        assert time.monotonic()<deadline,health
        time.sleep(.1)
    code=run('decompile',{'program':SMALL,'function':'mix'})['output']['code']
    assert 'must disappear on crash' not in code
    assert c.call('job_result',session=s,job=job)['effect']=='outcome_unknown'
    assert not psutil.pid_exists(before['engine_pid'])
