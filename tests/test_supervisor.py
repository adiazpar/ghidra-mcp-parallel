import collections
import json
import sqlite3
import threading
import time
import pytest
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


@pytest.fixture
def queued_supervisor(tmp_path, monkeypatch):
    s = object.__new__(Supervisor)
    s.lock = threading.Condition(threading.RLock())
    s.config = {'retained_jobs': 3, 'session_idle_seconds': 60, 'max_sessions': 2,
                'queue_limit': 8, 'per_session_jobs': 8, 'output_bytes': 4096, 'workers': 1}
    s.sessions = {}
    s.jobs = collections.OrderedDict()
    s.pending = collections.deque()
    s.active = set()
    s.known_programs = {}
    s.closed = False
    s.recovering = False
    s.generation = 'test-generation'
    s.db = sqlite3.connect(tmp_path / 'journal.sqlite')
    s.db.execute('CREATE TABLE jobs (id TEXT PRIMARY KEY,record TEXT NOT NULL)')
    clock = [10.0]
    monkeypatch.setattr(time, 'perf_counter', lambda: clock[0])
    yield s, clock
    s.db.close()


@pytest.mark.parametrize('operation', ['query', 'edit'])
@pytest.mark.parametrize('elapsed', [1.0, 2.0])
def test_expired_queued_jobs_are_not_dispatched(queued_supervisor, operation, elapsed):
    s, clock = queued_supervisor
    sid = s.new_session()['session']
    expired = s.submit(sid, operation, {}, 1)['id']
    following = s.submit(sid, 'query', {}, 60)['id']
    clock[0] += elapsed
    sent = []

    def transmit(message):
        sent.append(message)
        s.closed = True

    s.transmit = transmit
    s.schedule()
    assert [message['id'] for message in sent] == [following]
    result = s.get(sid, expired)
    assert result['status'] == 'timed_out'
    assert result['timeout_requested'] is True
    assert result['effect'] == 'none'
    assert 'started' not in result
    persisted = json.loads(s.db.execute(
        'SELECT record FROM jobs WHERE id=?', (expired,)).fetchone()[0])
    assert persisted['status'] == 'timed_out'
    assert expired not in s.pending and expired not in s.active


def test_job_expiring_while_waiting_for_worker_is_not_dispatched(queued_supervisor, monkeypatch):
    s, clock = queued_supervisor
    sid = s.new_session()['session']
    blocker = s.submit(sid, 'query', {}, 60)['id']
    s.pending.remove(blocker)
    s.jobs[blocker]['status'] = 'running'
    s.active.add(blocker)
    expired = s.submit(sid, 'edit', {}, 1)['id']
    following = s.submit(sid, 'query', {}, 60)['id']

    def finish_blocker(timeout):
        clock[0] += 2
        s.active.remove(blocker)
        s.jobs[blocker]['status'] = 'completed'

    monkeypatch.setattr(s.lock, 'wait', finish_blocker)
    sent = []

    def transmit(message):
        sent.append(message)
        s.closed = True

    s.transmit = transmit
    s.schedule()
    assert [message['id'] for message in sent] == [following]
    assert s.get(sid, expired)['status'] == 'timed_out'


def test_unexpired_queued_job_is_dispatched(queued_supervisor):
    s, clock = queued_supervisor
    sid = s.new_session()['session']
    job = s.submit(sid, 'edit', {}, 1)['id']
    clock[0] += .5
    sent = []

    def transmit(message):
        sent.append(message)
        s.closed = True

    s.transmit = transmit
    s.schedule()
    assert [message['id'] for message in sent] == [job]
    assert s.get(sid, job)['status'] == 'running'
