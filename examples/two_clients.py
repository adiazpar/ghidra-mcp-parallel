"""Run from the checkout: .venv/Scripts/python.exe -m examples.two_clients"""
from concurrent.futures import ThreadPoolExecutor
from service.client import Client


def analyze(function):
    client=Client()
    session=client.call('session_open',label=function)['session']
    try:
        result=client.run(session,'decompile',{'program':'/small.exe','function':function,'cache':False})
        if result['status']!='completed':raise RuntimeError(result)
        return {'job':result['id'],'program':result['program'],'output':result['output']}
    finally:
        client.call('session_close',session=session)


if __name__=='__main__':
    with ThreadPoolExecutor(2) as pool:
        for result in pool.map(analyze,('mix','sum_records')):
            print(result)
