"""Own an engine and all its descendants, including native decompilers."""
import os
import subprocess
import psutil


class OwnedProcess:
    def __init__(self, command, env, cwd, log, memory_mb):
        self.job = None
        if os.name == 'nt':
            import win32job
            self.job = win32job.CreateJobObject(None, '')
            limits = win32job.QueryInformationJobObject(self.job, win32job.JobObjectExtendedLimitInformation)
            limits['BasicLimitInformation']['LimitFlags'] = (
                win32job.JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE | win32job.JOB_OBJECT_LIMIT_JOB_MEMORY)
            limits['JobMemoryLimit'] = memory_mb * 1024 * 1024
            win32job.SetInformationJobObject(self.job, win32job.JobObjectExtendedLimitInformation, limits)
        self.process = subprocess.Popen(command, cwd=cwd, env=env, stdin=subprocess.DEVNULL,
                                        stdout=log, stderr=subprocess.STDOUT,
                                        creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0,
                                        start_new_session=os.name != 'nt')
        self.identity = psutil.Process(self.process.pid)
        try:
            if self.job:
                # Engine waits for our private handshake before initializing Ghidra or spawning children.
                win32job.AssignProcessToJobObject(self.job, int(self.process._handle))
        except BaseException:
            self.process.kill()
            self.process.wait()
            raise

    def stats(self):
        result = []
        try:
            processes = [self.identity] + self.identity.children(recursive=True)
            for p in processes:
                try:
                    m = p.memory_info()
                    result.append({'pid': p.pid, 'name': p.name(), 'rss': m.rss,
                                   'private': getattr(m, 'private', m.vms)})
                except psutil.Error:
                    pass
        except psutil.Error:
            pass
        return result

    def kill(self):
        if self.job:
            import win32job
            win32job.TerminateJobObject(self.job, 4)
        elif self.process.poll() is None:
            import signal
            os.killpg(self.process.pid, signal.SIGKILL)
        self.process.wait(timeout=20)

    def close(self):
        if self.process.poll() is None:
            self.kill()
        if self.job:
            self.job.Close()
            self.job = None
