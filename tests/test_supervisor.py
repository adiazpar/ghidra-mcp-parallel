import collections
import json
import sqlite3
import threading
import time
from service.supervisor import Supervisor


def test_journal_retention_and_session_expiry(tmp_path):
    s=object.__new__(Supervisor)
    s.lock=threading.Condition(threading.RLock())
    s.config={'retained_jobs':3,'session_idle_seconds':1}
    s.sessions={'expired':{'last_seen':time.perf_counter()-2},'live':{'last_seen':time.perf_counter()}}
    s.db=sqlite3.connect(tmp_path/'journal.sqlite')
    s.db.execute('CREATE TABLE jobs (id TEXT PRIMARY KEY,record TEXT NOT NULL)')
    s.jobs=collections.OrderedDict()
    for i in range(8):
        j={'id':str(i),'session':'expired','status':'completed','output':{'text':'retained output'}}
        s.jobs[j['id']]=j;s.persist(j)
    s.prune()
    assert list(s.jobs)==['5','6','7']
    assert s.db.execute('SELECT count(*) FROM jobs').fetchone()[0]==3
    s.expire_sessions()
    assert list(s.sessions)==['live']
    assert all('output' not in j and j['result_released'] for j in s.jobs.values())
    assert all('output' not in json.loads(row[0]) for row in s.db.execute('SELECT record FROM jobs'))
    s.db.close()
