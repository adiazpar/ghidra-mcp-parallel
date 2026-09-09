import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOCAL = ROOT / '.local'
CONFIG = LOCAL / 'config.json'
READS = frozenset({'query', 'decompile', 'decompile_batch', 'programs', 'capabilities'})
OPS = READS | {'project_open', 'project_close', 'program_open', 'program_import',
              'program_save', 'program_close', 'edit', 'analyze', 'script', 'export'}
TERMINAL = frozenset({'completed', 'failed', 'timed_out', 'cancelled'})


def contained(value):
    path = (ROOT / value).resolve()
    if not path.is_relative_to(ROOT):
        raise ValueError('Path must remain inside checkout')
    return path


def read_config():
    c = json.loads(CONFIG.read_text())
    if c['host'] != '127.0.0.1' or not 1024 <= c['port'] <= 65535 or c['port'] == 8080:
        raise ValueError('Explicit loopback port other than 8080 required')
    for key, low, high in [('workers', 1, 4), ('queue_limit', 1, 1024),
                           ('max_sessions', 1, 1024), ('max_programs', 1, 8),
                           ('retained_jobs', 1, 4096), ('output_bytes', 4096, 4194304),
                           ('cache_entries', 0, 256), ('per_session_jobs', 1, 128)]:
        if not low <= c[key] <= high:
            raise ValueError(f'Invalid {key}')
    if not 256 <= c['heap_mb'] <= 8192 or not c['heap_mb']+256 <= c['memory_mb'] <= 16384:
        raise ValueError('Memory budgets must be bounded; total must exceed JVM heap')
    if not 1 <= c['session_idle_seconds'] <= 86400 or not 1 <= c['cancel_grace_seconds'] <= 60:
        raise ValueError('Session lifetime and cancellation grace must be bounded')
    if len(c['token']) < 32:
        raise ValueError('Authentication token too short')
    return c


def child_environment():
    env = os.environ.copy()
    for name in ('TEMP', 'TMP', 'XDG_CACHE_HOME', 'XDG_CONFIG_HOME', 'XDG_DATA_HOME'):
        path = LOCAL / 'runtime' / name.lower()
        path.mkdir(parents=True, exist_ok=True)
        env[name] = str(path)
    # Prevent inherited Java switches and user-wide script paths from changing the owner.
    for name in ('JAVA_TOOL_OPTIONS', '_JAVA_OPTIONS', 'JDK_JAVA_OPTIONS', 'GHIDRA_INSTALL_DIR'):
        env.pop(name, None)
    return env
