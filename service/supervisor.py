import collections
import json
import os
import secrets
import socket
import sqlite3
import threading
import time
import uuid
from pathlib import Path

from .config import ROOT, LOCAL, READS, OPS, TERMINAL, child_environment, contained
from .process import OwnedProcess


class Supervisor:
    def __init__(self, config):
        self.config = config
        self.lock = threading.Condition(threading.RLock())
        self.send_lock = threading.Lock()
        self.recovery_lock = threading.Lock()
        self.sessions = {}
        self.jobs = collections.OrderedDict()
        self.pending = collections.deque()
        self.active = set()
        self.closed = False
        self.recovering = True
        self.engine = None
        self.connection = None
        self.generation = None
        self.last_error = None
        self.known_programs = {}
        self.restarts = 0
        self.last_log_prune = 0.0
        self.runtime = LOCAL / 'runtime'
        self.runtime.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.runtime / 'jobs.sqlite', check_same_thread=False)
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.execute('PRAGMA synchronous=FULL')
        self.db.execute('CREATE TABLE IF NOT EXISTS jobs (id TEXT PRIMARY KEY, record TEXT NOT NULL)')
        for jid, record in self.db.execute('SELECT id,record FROM jobs ORDER BY rowid'):
            j = json.loads(record)
            if j['status'] not in TERMINAL:
                j.update(status='failed', error='Supervisor restarted; job was not replayed',
                         effect='none' if j['op'] in READS or j['status'] == 'queued' else 'outcome_unknown',
                         finished=time.time())
            self.jobs[jid] = j
        for j in self.jobs.values():
            self.persist(j)
        self.manifest_path = self.runtime / 'manifest.json'
        self.manifest = json.loads(self.manifest_path.read_text()) if self.manifest_path.exists() else {'project': None, 'programs': []}
        self.log = open(self.runtime / 'engine.log', 'ab', buffering=0)
        self.start_engine()
        self.scheduler = threading.Thread(target=self.schedule, name='scheduler', daemon=True)
        self.scheduler.start()
        self.watchdog = threading.Thread(target=self.watch, name='watchdog', daemon=True)
        self.watchdog.start()
        self.restore()
        self.recovering = False

    def persist(self, job):
        self.db.execute('INSERT OR REPLACE INTO jobs VALUES (?,?)', (job['id'], json.dumps(job)))
        self.db.commit()

    def prune(self):
        done = [jid for jid, j in self.jobs.items() if j['status'] in TERMINAL]
        for jid in done[:-self.config['retained_jobs']]:
            del self.jobs[jid]
            self.db.execute('DELETE FROM jobs WHERE id=?', (jid,))
        self.db.commit()

    def start_engine(self):
        listener = socket.socket()
        listener.bind(('127.0.0.1', 0))
        listener.listen(1)
        listener.settimeout(90)
        secret = secrets.token_urlsafe(32)
        env = child_environment()
        env['SERVICE_ENGINE_SECRET'] = secret
        ghidra = contained(self.config['ghidra'])
        java = self.config['java']
        command = [java, '-Xshare:off', f"-Xmx{self.config['heap_mb']}m", '-XX:ActiveProcessorCount=4',
                   '-Djava.system.class.loader=ghidra.GhidraClassLoader', '-Djava.awt.headless=true',
                   '-Dfile.encoding=UTF-8', '-Duser.language=en', '-Duser.country=US',
                   '-Dcpu.core.limit=4', '-Dpython.console.encoding=UTF-8', '-Dlog4j.skipJansi=true',
                   f'-Duser.home={self.runtime / "home"}',
                   f'-Dapplication.settingsdir={self.runtime / "settings"}',
                   f'-Dapplication.cachedir={self.runtime / "cache"}',
                   f'-Dapplication.tempdir={self.runtime / "temp"}',
                   f'-Djava.io.tmpdir={self.runtime / "temp"}',
                   '-cp', str(ghidra / 'Ghidra/Framework/Utility/lib/Utility.jar'),
                   'ghidra.Ghidra', 'service.Engine', str(ROOT), str(listener.getsockname()[1])]
        # The dedicated installation is the only extension location this package touches.
        for path in ('home', 'settings', 'cache', 'temp'):
            (self.runtime / path).mkdir(exist_ok=True)
        self.engine = OwnedProcess(command, env, ROOT, self.log, self.config['memory_mb'])
        try:
            conn, _ = listener.accept()
            conn.settimeout(90)
            stream = conn.makefile('rb')
            hello = json.loads(stream.readline(4096))
            if hello.get('secret') != secret or hello.get('pid') != self.engine.process.pid:
                raise RuntimeError('Engine handshake rejected')
            conn.sendall((json.dumps(self.config) + '\n').encode())
            ready = json.loads(stream.readline(65536))
            if ready.get('event') != 'ready':
                raise RuntimeError(f'Engine startup failed: {ready}')
            conn.settimeout(None)
            self.connection = conn
            self.generation = ready['generation']
            threading.Thread(target=self.receive, args=(conn, stream, self.generation), daemon=True).start()
        except BaseException:
            self.engine.close()
            raise
        finally:
            listener.close()

    def transmit(self, message):
        with self.send_lock:
            self.connection.sendall((json.dumps(message) + '\n').encode())

    def receive(self, conn, stream, generation):
        try:
            while line := stream.readline(self.config['output_bytes'] + 65536):
                record = json.loads(line)
                with self.lock:
                    if generation != self.generation:
                        return
                    j = self.jobs.get(record.get('id'))
                    if not j or j['status'] in TERMINAL:
                        continue
                    if record['event'] == 'started':
                        j.update(backend_start_ns=record['backend_start_ns'], backend_thread=record['thread'])
                    elif record['event'] == 'result':
                        j.update(record)
                        if 'program' in record:
                            self.known_programs[record['program']['id']] = record['program']
                        j.pop('event', None)
                        j.update(finished=time.time(), elapsed_ms=(time.perf_counter()-j['submitted_mono'])*1000)
                        if j.get('timeout_requested') and j['status'] == 'cancelled':
                            j['status'] = 'timed_out'
                        self.active.discard(j['id'])
                        self.update_manifest(j)
                        if j['session'] not in self.sessions and not j['internal']:
                            j.pop('output', None)
                            j['result_released'] = True
                    self.persist(j)
                    self.prune()
                    self.lock.notify_all()
        except (OSError, ValueError) as exc:
            self.last_error = str(exc)
        finally:
            stream.close()
            conn.close()
            if not self.closed and generation == self.generation:
                self.recover_async('Engine connection lost')

    def update_manifest(self, j):
        if j['status'] != 'completed':
            return
        op, a = j['op'], j['args']
        if op == 'project_open':
            self.manifest['project'] = a
        elif op == 'project_close':
            self.manifest = {'project': None, 'programs': []}
        elif op in ('program_import', 'program_open'):
            if 'id' not in j['output']:
                return
            name = j['output']['id']
            if name not in self.manifest['programs']:
                self.manifest['programs'].append(name)
        elif op == 'program_close' or (op == 'script' and j.get('effect') == 'deleted'):
            if a['program'] in self.manifest['programs']:
                self.manifest['programs'].remove(a['program'])
        else:
            return
        tmp = self.manifest_path.with_suffix('.tmp')
        tmp.write_text(json.dumps(self.manifest))
        tmp.replace(self.manifest_path)

    def restore(self):
        manifest = json.loads(json.dumps(self.manifest))
        if manifest['project']:
            self.internal('project_open', manifest['project'])
            for path in manifest['programs']:
                self.internal('program_open', {'path': path})

    def internal(self, op, args):
        j = self.submit('_supervisor', op, args, 120, internal=True)
        with self.lock:
            deadline = time.perf_counter() + 125
            while self.jobs[j['id']]['status'] not in TERMINAL:
                remaining = deadline-time.perf_counter()
                if remaining <= 0:
                    raise TimeoutError('Internal lifecycle operation timed out')
                self.lock.wait(remaining)
            result = self.jobs[j['id']]
            if result['status'] != 'completed':
                raise RuntimeError(result.get('error', 'Lifecycle failure'))
            return result

    def new_session(self, label=''):
        with self.lock:
            self.expire_sessions()
            if len(self.sessions) >= self.config['max_sessions']:
                raise ValueError('Session limit reached')
            sid = uuid.uuid4().hex
            self.sessions[sid] = {'last_seen': time.perf_counter(), 'label': label[:128]}
            return {'session': sid, 'idle_seconds': self.config['session_idle_seconds']}

    def session(self, sid):
        if sid not in self.sessions:
            raise ValueError('Unknown or expired session')
        self.sessions[sid]['last_seen'] = time.perf_counter()

    def expire_sessions(self):
        now = time.perf_counter()
        for sid, s in list(self.sessions.items()):
            if now-s['last_seen'] > self.config['session_idle_seconds']:
                self.close_session(sid)

    def close_session(self, sid):
        with self.lock:
            self.session(sid)
            for j in list(self.jobs.values()):
                if j['id'] not in self.jobs:
                    continue
                if j['session'] == sid:
                    if j['status'] not in TERMINAL:
                        self.cancel(sid, j['id'])
                    else:
                        j.pop('output', None)
                        j['result_released'] = True
                        self.persist(j)
            self.sessions.pop(sid)
            self.prune()
            return {'closed': True}

    def submit(self, sid, op, args, timeout=60, internal=False):
        with self.lock:
            if self.closed:
                raise ValueError('Service is shutting down')
            if not internal:
                self.session(sid)
                if self.recovering:
                    raise ValueError('Engine recovering; retry after health reports ready')
            if op not in OPS:
                raise ValueError('Unknown operation')
            if not 0.05 <= timeout <= 3600:
                raise ValueError('Timeout must be 0.05..3600 seconds, including queue time')
            if len(json.dumps(args).encode()) > min(self.config['output_bytes'], 262144):
                raise ValueError('Request too large')
            if len(self.pending) >= self.config['queue_limit']:
                raise ValueError('queue_full')
            if sum(j['session'] == sid and j['status'] not in TERMINAL for j in self.jobs.values()) >= self.config['per_session_jobs']:
                raise ValueError('Session outstanding job limit')
            jid = uuid.uuid4().hex
            j = {'id': jid, 'session': sid, 'op': op, 'args': args, 'status': 'queued',
                 'submitted': time.time(), 'submitted_mono': time.perf_counter(),
                 'timeout': timeout, 'effect': 'none', 'internal': internal, 'ghidra': '12.1.3',
                 'last_known_program': self.known_programs.get(args.get('program'))}
            self.jobs[jid] = j
            self.persist(j)  # durable acceptance precedes dispatch
            self.prune()
            self.pending.append(jid)
            self.lock.notify_all()
            return {'id': jid, 'status': 'queued'}

    def schedule(self):
        while not self.closed:
            with self.lock:
                if not self.pending:
                    self.lock.wait(.1)
                    continue
                jid = self.pending[0]
                j = self.jobs[jid]
                if j['status'] != 'queued':
                    self.pending.popleft()
                    continue
                if self.recovering and not j['internal']:
                    self.lock.wait(.1)
                    continue
                read = j['op'] in READS
                # FIFO admission with finite per-session quotas; later readers cannot starve a writer.
                if len(self.active) >= self.config['workers'] or (self.active and
                    (not read or any(self.jobs[x]['op'] not in READS for x in self.active))):
                    self.lock.wait(.1)
                    continue
                self.pending.popleft()
                # The watchdog may not have observed a deadline reached in the queue.
                if time.perf_counter()-j['submitted_mono'] >= j['timeout']:
                    j.update(status='timed_out', timeout_requested=True, finished=time.time())
                    self.persist(j)
                    self.prune()
                    self.lock.notify_all()
                    continue
                self.active.add(jid)
                j.update(status='running', started=time.time(), queue_ms=(time.perf_counter()-j['submitted_mono'])*1000,
                         generation=self.generation)
                self.persist(j)
                try:
                    self.transmit({'id': jid, 'op': j['op'], 'args': j['args']})
                except OSError as exc:
                    self.recover_async(str(exc))

    def get(self, sid, jid, result=True):
        with self.lock:
            self.session(sid)
            j = self.jobs.get(jid)
            if not j or j['session'] != sid:
                raise ValueError('Unknown job for this session')
            copy = json.loads(json.dumps(j))
            if not result:
                copy.pop('output', None)
            copy.pop('submitted_mono', None)
            return copy

    def cancel(self, sid, jid, timed_out=False):
        with self.lock:
            self.session(sid)
            j = self.jobs.get(jid)
            if not j or j['session'] != sid:
                raise ValueError('Unknown job for this session')
            if j['status'] in TERMINAL:
                return {'status': j['status']}
            if timed_out:
                j['timeout_requested'] = True
            if j['status'] == 'queued':
                self.pending.remove(jid)
                j.update(status='timed_out' if timed_out else 'cancelled', finished=time.time())
            elif not j.get('cancel_requested'):
                j['cancel_requested'] = time.perf_counter()
                try:
                    self.transmit({'op': 'cancel', 'id': jid})
                except OSError:
                    self.recover_async('Cancellation transport failed')
            self.persist(j)
            self.prune()
            self.lock.notify_all()
            return {'status': j['status'], 'cancellation': 'cooperative',
                    'escalation': 'engine-wide recovery if grace period expires'}

    def watch(self):
        while not self.closed:
            time.sleep(.1)
            with self.lock:
                if self.closed:
                    return
                if self.log.tell() > 16 * 1024 * 1024:
                    self.log.seek(0)
                    self.log.truncate()
                if time.perf_counter()-self.last_log_prune>60:
                    for prefix in ('ghidra.log-', 'scripts.log-'):
                        archives=sorted(self.runtime.glob(prefix+'*.log'),key=lambda p:p.stat().st_mtime,reverse=True)
                        for path in archives[4:]:
                            try:path.unlink()
                            except OSError:pass
                    self.last_log_prune=time.perf_counter()
                self.expire_sessions()
                for j in list(self.jobs.values()):
                    if j['status'] in TERMINAL or j['internal']:
                        continue
                    if time.perf_counter()-j['submitted_mono'] > j['timeout'] and not j.get('timeout_requested'):
                        if j['session'] in self.sessions:
                            self.cancel(j['session'], j['id'], True)
                    if j.get('cancel_requested') and time.perf_counter()-j['cancel_requested'] > self.config['cancel_grace_seconds']:
                        self.recover_async('Uncooperative job exceeded cancellation grace')

    def recover_async(self, reason):
        if self.closed or self.recovering:
            return
        self.recovering = True
        threading.Thread(target=self.recover, args=(reason,), daemon=True).start()

    def recover(self, reason):
        with self.recovery_lock:
            self.recovering = True
            with self.lock:
                self.generation = None  # discard events from the previous owner
                for j in self.jobs.values():
                    if j['status'] not in TERMINAL:
                        prior = j['status']
                        j.update(status='timed_out' if j.get('timeout_requested') else 'failed',
                                 error=reason, effect='none' if prior == 'queued' or j['op'] in READS else 'outcome_unknown',
                                 finished=time.time(), persistence='last_durable_state_after_recovery')
                        self.persist(j)
                self.pending.clear()
                self.active.clear()
                self.lock.notify_all()
            try:
                self.engine.close()  # wait for all owned processes before opening the project again
                self.start_engine()
                self.restore()
                self.restarts += 1
                self.last_error = reason
                self.recovering = False
                with self.lock:
                    self.lock.notify_all()
            except BaseException as exc:
                self.last_error = f'Recovery failed: {exc}'

    def health(self):
        with self.lock:
            return {'state': 'stopping' if self.closed else 'recovering' if self.recovering else 'ready',
                    'supervisor_pid': os.getpid(),
                    'generation': self.generation, 'engine_pid': self.engine.process.pid,
                    'sessions': len(self.sessions), 'queued': len(self.pending), 'running': len(self.active),
                    'retained_jobs': len(self.jobs), 'workers': self.config['workers'],
                    'restarts': self.restarts, 'last_error': self.last_error,
                    'owned_processes': self.engine.stats(), 'manifest': self.manifest}

    def shutdown(self):
        with self.recovery_lock:
            with self.lock:
                self.closed = True
                for j in self.jobs.values():
                    if j['status'] not in TERMINAL:
                        prior = j['status']
                        j.update(status='cancelled' if prior == 'queued' else 'failed',
                                 error='Service shutdown; no replay',
                                 effect='none' if prior == 'queued' or j['op'] in READS else 'outcome_unknown',
                                 finished=time.time())
                        self.persist(j)
                self.lock.notify_all()
                try:
                    self.transmit({'op': 'shutdown'})
                except OSError:
                    pass
            try:
                self.engine.process.wait(timeout=15)
            except Exception:
                self.engine.kill()
            self.engine.close()
            self.log.close()
