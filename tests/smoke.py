"""Live smoke validation. Uses only the packaged MCP endpoint and repository fixtures."""
import concurrent.futures
import json
from pathlib import Path
from service.client import Client

c = Client()
s = c.call('session_open', label='smoke')['session']
p = '/small.exe'
report = []

def run(op, args, success=True):
    r = c.run(s, op, args)
    report.append(r)
    print(op, args.get('kind', args.get('name', '')), r['status'], r.get('error', ''))
    if success:
        assert r['status'] == 'completed', r
    return r

def version():
    return run('programs', {})['output']['loaded'][0]['version']

try:
    caps = run('capabilities', {})
    print(json.dumps(caps['output']['script_providers']))
    for kind in caps['output']['queries']:
        run('query', {'program': p, 'kind': kind, 'function': 'mix', 'address': '140001064'})
    baseline = run('decompile', {'program': p, 'function': 'mix', 'cache': False})
    v = baseline['program']['version']
    r = run('edit', {'program': p, 'expected_version': v, 'changes': [
        {'op': 'rename_function', 'function': 'mix', 'name': 'mix_named'}]})
    run('edit', {'program': p, 'expected_version': v, 'changes': [
        {'op': 'rename_function', 'function': 'mix_named', 'name': 'stale'}]}, False)
    r = run('edit', {'program': p, 'expected_version': r['program']['version'], 'changes': [
        {'op': 'rename_function', 'function': 'mix_named', 'name': 'mix'},
        {'op': 'define_type', 'declaration': 'typedef struct Pair { unsigned int key; unsigned int value; } Pair;'}]})
    for name in ('ContextProbe.java', 'jython_probe.py', 'PromptProbe.java'):
        r = run('script', {'program': p, 'expected_version': r['program']['version'],
                           'name': name, 'args': ['fixture-arg'] if name != 'PromptProbe.java' else [],
                           'paths': ['fixtures/scripts'], 'address': '140001064',
                           'selection': [['140001064', '140001067']]})
        print(json.dumps(r.get('output'), indent=2))
finally:
    Path('.local/smoke.json').write_text(json.dumps(report, indent=2))
    c.call('session_close', session=s)
