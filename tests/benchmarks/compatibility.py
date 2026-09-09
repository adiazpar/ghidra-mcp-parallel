"""Compare Java/Jython/headless lifecycle and failure persistence using ordinary invocation."""
import json
import subprocess
import time
from pathlib import Path
from service.config import ROOT,LOCAL,read_config,child_environment
from service.client import Client
from service.process import OwnedProcess


def invocation(version,name,arguments):
    config=read_config();ghidra=LOCAL/f'ghidra_{version}_PUBLIC'
    directory=LOCAL/'compatibility'/version
    directory.mkdir(parents=True,exist_ok=True)
    project=ROOT/'runtime/compatibility';project.mkdir(parents=True,exist_ok=True)
    cmd=[config['java'],'-Xshare:off','-Xmx4096m','-XX:ActiveProcessorCount=4',
         '-Djava.system.class.loader=ghidra.GhidraClassLoader','-Dcpu.core.limit=4','-Dfile.encoding=UTF-8','-Djava.awt.headless=true']
    for prop,folder in [('user.home','home'),('application.settingsdir','settings'),('application.cachedir','cache'),('application.tempdir','temp'),('java.io.tmpdir','temp')]:
        (directory/folder).mkdir(exist_ok=True);cmd.append(f'-D{prop}={directory/folder}')
    cmd+=['-cp',str(ghidra/'Ghidra/Framework/Utility/lib/Utility.jar'),'ghidra.Ghidra','ghidra.app.util.headless.AnalyzeHeadless',
          str(project),name,'-scriptPath',str(ROOT/'tests/fixtures/scripts'),'-max-cpu','4',
          '-log',str(directory/'ghidra.log'),'-scriptlog',str(directory/'scripts.log'),*arguments]
    output=directory/f'{time.time_ns()}.log'
    with output.open('wb') as log:
        child=OwnedProcess(cmd,child_environment(),ROOT,log,6144)
        try:code=child.process.wait(120)
        finally:child.close()
    return code,output.read_text(errors='replace')


def main():
    results=[]
    expected=['headless=true','selection=4','args=fixture-arg','nested=shared-with-nested',
              'nestedArgs=nested-arg','probe-error-stream','jython-headless=True',
              'jython-args=fixture-arg','jython-error-stream','plain-nested=from-jython',
              'prompt=property-value','context-complete']
    c=Client();sid=c.call('session_open')['session']
    try:
        programs=c.run(sid,'programs',{})['output']['loaded'];p=next(x for x in programs if x['id']=='/small.exe')
        service=c.run(sid,'script',{'program':p['id'],'expected_version':p['version'],'paths':['tests/fixtures/scripts'],
                                  'name':'BaselineContext.java'})
        assert service['status']=='completed',service
        output=service['output']['stdout']+service['output']['stderr']
        assert all(x in output for x in expected),output
        results.append({'mode':'service','matched_context':expected,'result':service})
        for version in ('12.1.3','11.3.2'):
            name='compat_'+version.replace('.','_')+'_'+str(int(time.time()))
            code,text=invocation(version,name,['-import',str(LOCAL/'fixtures/small.exe'),'-preScript','DisableAnalysis.java',
                                               '-postScript','BaselineContext.java','-postScript','LifecyclePost.java'])
            assert code==0 and all(x in text for x in expected),text[-3000:]
            assert 'disabled=true' in text and 'post-analysis-enabled=false' in text
            code,failed=invocation(version,name,['-process','small.exe','-noanalysis','-postScript','FailAfterEdit.java'])
            assert 'fixture failure' in failed and 'before-failure' in failed
            code,saved=invocation(version,name,['-process','small.exe','-noanalysis','-postScript','CheckSaved.java'])
            assert 'saved-comment=script partial effect' in saved,saved[-2000:]
            results.append({'mode':'analyzeHeadless','version':version,'matched_context':expected,
                            'analysis_disable':True,'failed_script_logs_error':True,'failed_script_partial_changes_saved':True})
    finally:c.call('session_close',session=sid)
    (LOCAL/'compatibility/report.json').write_text(json.dumps(results,indent=2))
    print('Service and both ordinary headless versions passed the context and lifecycle comparison')


if __name__=='__main__':main()
