# Development

Run all commands from the repository root. Production use and plugin installation
are covered in [installation](INSTALLATION.md).

Prerequisites: JDK 21.0.11 on PATH, Python/uv for bootstrap, and approximately 2 GiB
for the local distribution and environment. Validation fixture builds additionally
require MSVC 14.44.35207 x64 Build Tools. All runtime dependencies are pinned in
`toolchain.json` and `requirements.lock`.

```powershell
powershell -NoProfile -File tools/install.ps1 -Port 18765 -Workers 4
powershell -NoProfile -File tools/service.ps1 start
powershell -NoProfile -File tools/service.ps1 status
powershell -NoProfile -File tools/service.ps1 stop
```

Installation downloads and verifies Ghidra 12.1.3 and installs its bundled Jython
extension only inside `.local/`. Configuration and a random authentication token
are written to `.local/config.json`, with Windows permissions restricted to the
current user. No global MCP configuration is edited. The selected port must be
unused; no unrelated process is stopped to free it. Stop this service before
rebuilding/installing its engine.

`start` launches one supervisor, which starts one engine JVM. Multiple clients
connect to that owner; they never start a JVM themselves. `status` reports startup,
engine generation, bounded queues, sessions, loaded targets and owned process memory.
Engine crashes recover behind the same endpoint. Restarted jobs are not replayed.
Default successful edits/scripts save to disk; explicit `save:false` changes remain
volatile. Save desired volatile changes before stopping or restarting the engine.

## Connect clients

Use the URL `http://127.0.0.1:18765/mcp` and an `Authorization: Bearer <token>` header,
where the token comes from `.local/config.json`. Use the same endpoint for every
agent. Client-specific configuration belongs to you; installation does not change
any existing client, Ghidra installation or project.

For clients that require stdio, configure the project-local Python interpreter and
forwarding adapter. Replace the example path with this checkout's actual path:

```json
{
  "mcpServers": {
    "shared-ghidra": {
      "command": "C:/path/to/checkout/.venv/Scripts/python.exe",
      "args": ["C:/path/to/checkout/bridge_mcp_ghidra.py"]
    }
  }
}
```

The adapter reads the local configuration and forwards MCP requests to the running
service. It has no alternate analysis backend. The old `--ghidra-server` URL and
unauthenticated port 8080 bridge have been removed.

## First target and two clients

```powershell
powershell -NoProfile -File tests/build_fixtures.ps1
.venv/Scripts/python.exe -m tests.prepare
.venv/Scripts/python.exe -m examples.two_clients
```

For your own repository-local target, call `session_open`, submit `project_open`,
then `program_import`. Poll `job_result` with the returned job ID. The import result
contains the explicit program ID used for all subsequent requests. Use
`program_open` for an existing file in the service-owned project. Only one writable
project is open at a time; close loaded targets before switching projects.

```python
from service.client import Client
c = Client()
s = c.call('session_open', label='analysis')['session']
r = c.run(s, 'decompile', {
    'program': '/small.exe', 'function': 'mix', 'cache': False
})
assert r['status'] == 'completed', r
print(r['output']['code'])
c.call('session_close', session=s)
```

[API contract](API.md) covers every query, edit, script, lifecycle operation,
argument, conflict check, retention limit and cancellation outcome.
[Architecture](ARCHITECTURE.md) explains ownership and Ghidra synchronization.
[Capability matrix](CAPABILITIES.md) records tested headless behavior and limits.

## Validate and package

The tests are grouped by purpose: `test_live.py` exercises the running service;
`test_supervisor.py` and `test_plugin.py` check local contracts. Synthetic C and
Java/Jython inputs live in `tests/fixtures/`, their build command is
`tests/build_fixtures.ps1`, and `tests.prepare` imports disposable targets.
`tests/benchmarks/` contains throughput, mixed-workload and compatibility runners.
`tests/install_smoke.ps1 -Root <new-disposable-directory>` checks a fresh private
runtime, repeated updates, configuration preservation and MCP startup. It downloads
its own dependencies and runs in hosted CI; never point it at an existing installation.

Start the isolated service first. Validation refuses to replace a project other
than the disposable `validation` / `validation_*` projects. Rebuilt fixture hashes
are checked; if they changed, validation saves and closes the old disposable project
and imports into a fresh one. It never reuses a stale analyzed binary for comparison.

```powershell
powershell -NoProfile -File tools/validate.ps1
powershell -NoProfile -File tools/validate.ps1 -Benchmarks
powershell -NoProfile -File tools/package.ps1
```

The full benchmark also needs the separate Ghidra 11.3.2 comparison archive. Run
`tools/install.ps1 -Comparison` while the service is stopped to download, verify and
extract it under `.local/ghidra_11.3.2_PUBLIC`. It never opens
projects from your existing setup. Benchmarking restarts only this packaged service
while measuring worker counts 1, 2 and 4 and restores its configuration afterwards.

The ZIP and checksum are written to `dist/`. It includes source, the built engine,
fixtures, tests and documentation. It excludes tokens, databases, runtime state,
downloads, logs and local evidence. No release is published automatically.

See [measured validation](VALIDATION.md) for benchmark results and their limits.
