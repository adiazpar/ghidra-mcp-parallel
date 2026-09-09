import concurrent.futures
import json
import time
from service.client import Client
from service.config import LOCAL
from tests.benchmarks.measure import sessions_measure,summary


def main():
    c=Client();sessions=[c.call('session_open',label='mixed')['session'] for _ in range(4)]
    records=[];start=time.perf_counter()
    try:
        for repeat in range(12):
            p=next(x for x in c.run(sessions[0],'programs',{})['output']['loaded'] if x['id']=='/small.exe')
            jobs=[]
            for sid,op,args in [
                (sessions[0],'decompile',{'program':'/large.exe','function':f'work_{80+repeat:03d}','cache':False}),
                (sessions[1],'query',{'program':'/small.exe','kind':'symbols'}),
                (sessions[2],'edit',{'program':'/small.exe','expected_version':p['version'],'changes':[{'op':'comment','address':'140001064','text':f'mixed-{repeat}'}]}),
                (sessions[3],'decompile',{'program':'/small.exe','function':'mix','cache':False})]:
                jobs.append((sid,c.call('job_submit',session=sid,operation=op,arguments=args)['id']))
            with concurrent.futures.ThreadPoolExecutor(4) as pool:
                batch=list(pool.map(lambda pair:Client().wait(*pair),jobs))
            assert all(r['status']=='completed' for r in batch),batch
            assert batch[2]['backend_start_ns']>=max(batch[i]['backend_end_ns'] for i in (0,1))
            assert batch[3]['backend_start_ns']>=batch[2]['backend_end_ns']
            records.extend(batch)
        result={'summary':summary(records,time.perf_counter()-start),'jobs':records,'health':c.call('service_health')}
        (LOCAL/'measurements/mixed.json').write_text(json.dumps(result,indent=2))
        print(result['summary'])
    finally:
        for sid in sessions:c.call('session_close',session=sid)
    print('Session scaling points:',len(sessions_measure()))


if __name__=='__main__':main()
