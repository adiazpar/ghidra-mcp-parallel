"""Prepare synthetic targets only; refuses to replace a non-validation project."""
from pathlib import Path
import hashlib
import uuid
from service.client import Client


def main():
    c=Client();sid=c.call('session_open',label='validation setup')['session']
    try:
        def run(op,args):
            r=c.run(sid,op,args,600)
            if r['status']!='completed':raise RuntimeError(r)
            return r
        current=run('programs',{})['output']
        if current['project'] is not None and current['project']!='validation' and not current['project'].startswith('validation_'):
            raise RuntimeError('Validation requires a disposable validation project; current project is left untouched')
        refresh=False
        for name in ('small.exe','large.exe'):
            if '/'+name in current['files']:
                loaded=run('program_open',{'path':'/'+name})['output']
                digest=hashlib.file_digest(Path('.local/fixtures',name).open('rb'),'sha256').hexdigest()
                refresh |= loaded['binary_sha256']!=digest
        if refresh:
            # Preserve the prior disposable project, including any edited fixture state.
            for p in run('programs',{})['output']['loaded']:
                run('program_close',{'program':p['id'],'expected_version':p['version']})
            run('project_close',{})
            current['project']=None
        if current['project'] is None:
            run('project_open',{'name':'validation_'+uuid.uuid4().hex[:12],'directory':'runtime/projects'})
        for name in ('small.exe','large.exe'):
            current=run('programs',{})['output']
            if '/'+name not in current['files']:run('program_import',{'file':'.local/fixtures/'+name})
            elif not any(p['id']=='/'+name for p in current['loaded']):run('program_open',{'path':'/'+name})
    finally:c.call('session_close',session=sid)


if __name__=='__main__':main()
