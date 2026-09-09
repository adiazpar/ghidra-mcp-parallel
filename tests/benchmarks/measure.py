"""Reproducible local benchmark; owns only this checkout's packaged service and fixtures."""
import base64
import concurrent.futures
import hashlib
import json
import platform
import statistics
import subprocess
import time
from pathlib import Path
import psutil
from service.client import Client
from service.config import ROOT, LOCAL, CONFIG, read_config, child_environment
from service.process import OwnedProcess

OUT=LOCAL/'measurements'
OUT.mkdir(exist_ok=True)


def control(action):
    # Detached Windows descendants may inherit a pipe handle; use a file rather than
    # waiting for EOF on captured stdout from the launcher.
    with open(OUT/'control.log','ab') as log:
        subprocess.run(['powershell','-NoProfile','-File',str(ROOT/'tools/service.ps1'),action],cwd=ROOT,
                       check=True,stdout=log,stderr=log,stdin=subprocess.DEVNULL,
                       creationflags=subprocess.CREATE_NO_WINDOW)
    if action=='stop':
        deadline=time.monotonic()+30
        pid=int((LOCAL/'runtime/supervisor.pid').read_text().strip())
        while psutil.pid_exists(pid) and time.monotonic()<deadline:time.sleep(.1)
        if psutil.pid_exists(pid):raise RuntimeError('Owned supervisor did not exit')
    elif action=='start':
        deadline=time.monotonic()+120
        while time.monotonic()<deadline:
            try:
                if Client().call('service_health')['state']=='ready':return
            except Exception:pass
            time.sleep(.2)
        raise RuntimeError('Startup timed out')


def summary(records,elapsed):
    latency=[r['elapsed_ms'] for r in records]
    return {'requests':len(records),'wall_seconds':elapsed,'requests_per_second':len(records)/elapsed,
            'latency_median_ms':statistics.median(latency),'latency_p95_ms':sorted(latency)[int((len(latency)-1)*.95)],
            'queue_median_ms':statistics.median(r['queue_ms'] for r in records),
            'compute_median_ms':statistics.median(r['compute_ms'] for r in records)}


def worker_benchmark(workers):
    c=Client();sessions=[c.call('session_open',label='benchmark')['session'] for _ in range(8)]
    records=[]
    names=[f'work_{i:03d}' for i in range(20,44)]
    try:
        first=c.run(sessions[0],'decompile',{'program':'/large.exe','function':names[0],'cache':False,'coalesce':False})
        assert first['status']=='completed',first
        baseline={}
        for name in names:
            r=c.run(sessions[0],'decompile',{'program':'/large.exe','function':name,'cache':False,'coalesce':False})
            assert r['status']=='completed',r
            baseline[name]=r['output']['code']
        for repeat in range(3):
            def task(pair):
                i,name=pair
                return Client().run(sessions[i%8],'decompile',{'program':'/large.exe','function':name,'cache':False,'coalesce':False})
            start=time.perf_counter()
            with concurrent.futures.ThreadPoolExecutor(8) as pool:batch=list(pool.map(task,enumerate(names)))
            elapsed=time.perf_counter()-start
            for name,r in zip(names,batch):
                assert r['status']=='completed',r
                assert r['output']['code']==baseline[name],name
            records.append({'repeat':repeat,'summary':summary(batch,elapsed),'jobs':batch,'health':c.call('service_health')})
        batch_start=time.perf_counter()
        batched=c.run(sessions[0],'decompile_batch',{'program':'/large.exe','functions':names,'cache':False,'coalesce':False})
        batch_wall=time.perf_counter()-batch_start
        assert batched['status']=='completed',batched
        # Coalescing is measured separately from normal reads and result-cache hits.
        def identical(i):
            return Client().run(sessions[i],'decompile',{'program':'/large.exe','function':'work_240','cache':False,'coalesce':True})
        with concurrent.futures.ThreadPoolExecutor(8) as pool:coalesced=list(pool.map(identical,range(8)))
        assert all(r['status']=='completed' for r in coalesced)
        c.run(sessions[0],'decompile',{'program':'/large.exe','function':'work_250'})
        cached=c.run(sessions[0],'decompile',{'program':'/large.exe','function':'work_250'})
        assert cached['output']['cache_hit']
        result={'workers':workers,'first_request':first,'repeats':records,'batch_seconds':batch_wall,
                'batch_job':batched,'coalesced':coalesced,'cache_hit':cached,'baseline':baseline}
        (OUT/f'workers-{workers}.json').write_text(json.dumps(result,indent=2))
        return {k:v for k,v in result.items() if k not in ('baseline','batch_job','coalesced','first_request','repeats','cache_hit')} | {
            'first_request_ms':first['elapsed_ms'],'repeats':[x['summary'] for x in records],
            'owned_rss_bytes':sum(x['rss'] for x in records[-1]['health']['owned_processes']),
            'coalesced_jobs':sum(r['output'].get('coalesced',False) for r in coalesced)}
    finally:
        for sid in sessions:c.call('session_close',session=sid)


def sessions_measure():
    c=Client();ids=[];records=[]
    def storage():return sum(p.stat().st_size for p in (ROOT/'runtime/projects').rglob('*') if p.is_file())
    try:
        initial=c.call('service_health')['sessions']
        for n in [0,8,32,64,100]:
            while len(ids)<n:ids.append(c.call('session_open',label='scaling')['session'])
            h=c.call('service_health')
            records.append({'new_sessions':n,'project_bytes':storage(),'health':h,
                            'supervisor_rss':psutil.Process(h['supervisor_pid']).memory_info().rss})
        return records
    finally:
        for sid in ids:c.call('session_close',session=sid)
        records.append({'after_close':c.call('service_health'),'project_bytes':storage()})
        (OUT/'sessions.json').write_text(json.dumps(records,indent=2))


def baseline(version):
    c=Client();sid=c.call('session_open')['session']
    names=[f'work_{i:03d}' for i in range(20,28)]
    expected={name:c.run(sid,'decompile',{'program':'/large.exe','function':name,'cache':False,'coalesce':False})['output']['code'] for name in names}
    c.call('session_close',session=sid)
    ghidra=LOCAL/f'ghidra_{version}_PUBLIC'
    directory=OUT/f'baseline-{version}'
    directory.mkdir(exist_ok=True)
    project=ROOT/'runtime/baselines'
    project.mkdir(parents=True,exist_ok=True)
    config=read_config()
    options=[config['java'],'-Xshare:off','-Xmx4096m','-XX:ActiveProcessorCount=4',
             '-Djava.system.class.loader=ghidra.GhidraClassLoader','-Dcpu.core.limit=4',
             '-Dfile.encoding=UTF-8','-Djava.awt.headless=true','-Dpython.console.encoding=UTF-8']
    for prop,folder in [('user.home','home'),('application.settingsdir','settings'),('application.cachedir','cache'),('application.tempdir','temp'),('java.io.tmpdir','temp')]:
        (directory/folder).mkdir(exist_ok=True);options.append(f'-D{prop}={directory/folder}')
    options+=['-cp',str(ghidra/'Ghidra/Framework/Utility/lib/Utility.jar'),'ghidra.Ghidra','ghidra.app.util.headless.AnalyzeHeadless',
              str(project),f'baseline_{version.replace(".","_")}_{int(time.time())}',
              '-import',str(LOCAL/'fixtures/large.exe'),'-scriptPath',str(ROOT/'tests/fixtures/scripts'),
              '-postScript','Baseline.java',*names,'-max-cpu','4','-log',str(directory/'application.log'),
              '-scriptlog',str(directory/'script.log')]
    with open(directory/'console.log','wb') as log:
        start=time.perf_counter();owned=OwnedProcess(options,child_environment(),ROOT,log,6144)
        peaks={}
        try:
            while owned.process.poll() is None:
                for p in owned.stats():
                    peaks[p['pid']]=max(peaks.get(p['pid'],0),p['rss'])
                if time.perf_counter()-start>300:raise TimeoutError('Baseline timeout')
                time.sleep(.1)
            assert owned.process.returncode==0
        finally:owned.close()
        elapsed=time.perf_counter()-start
    text=(directory/'console.log').read_text(errors='replace')
    outputs={};compute={}
    for line in text.splitlines():
        if 'BASELINE|' in line:
            parts=line.split('BASELINE|',1)[1].split('|')
            name=parts[0];compute[name]=float(parts[1]);outputs[name]=base64.b64decode(parts[2].split()[0]).decode()
    assert set(outputs)==set(names),text[-3000:]
    matching={name:outputs[name].replace('\r\n','\n')==expected[name].replace('\r\n','\n') for name in names}
    if version=='12.1.3':assert all(matching.values()),matching
    result={'version':version,'wall_seconds':elapsed,'peak_owned_rss_sum':sum(peaks.values()),'compute_ms':compute,'matching_service':matching,
            'fixture_sha256':hashlib.file_digest((LOCAL/'fixtures/large.exe').open('rb'),'sha256').hexdigest(),'outputs':outputs}
    (OUT/f'baseline-{version}.json').write_text(json.dumps(result,indent=2))
    return {k:v for k,v in result.items() if k!='outputs'}


def main():
    config=read_config();original=config.copy()
    report={'machine':{'system':platform.platform(),'cpu':platform.processor(),'logical_cpus':psutil.cpu_count(),'ram_bytes':psutil.virtual_memory().total},
            'python':platform.python_version(),'workers':[]}
    try:
        for workers in (1,2,4):
            control('stop');config['workers']=workers;CONFIG.write_text(json.dumps(config,indent=2));control('start')
            report['workers'].append(worker_benchmark(workers))
            print('Measured workers',workers,flush=True)
        report['sessions']=sessions_measure()
        for version in ('12.1.3','11.3.2'):
            report.setdefault('headless',[]).append(baseline(version));print('Measured baseline',version,flush=True)
    finally:
        control('stop');CONFIG.write_text(json.dumps(original,indent=2));control('start')
        (OUT/'report.json').write_text(json.dumps(report,indent=2))


if __name__=='__main__':main()
