"""Distribution contracts and the external-workspace script staging boundary."""
import importlib.util
import json
from pathlib import Path
import pytest
from tools.runtime_payload import install, payload_files

ROOT = Path(__file__).resolve().parents[1]


def test_version_and_shared_mcp_contract():
    version = (ROOT / 'VERSION').read_text().strip()
    for host in ('.claude-plugin', '.codex-plugin'):
        manifest = json.loads((ROOT / host / 'plugin.json').read_text())
        assert manifest['version'] == version
        assert manifest['name'] == 'ghidra-mcp-parallel'
        assert manifest['mcpServers'] == './.mcp.json'
    command = json.loads((ROOT / '.mcp.json').read_text())['mcpServers']['ghidra']
    assert command['command'] == 'powershell.exe'
    assert 'service.server' not in str(command)
    assert 'bridge_mcp_ghidra.py' in str(command)
    assert 'C:\\Users' not in str(command)


def test_staging_allows_external_workspace_but_not_escape(tmp_path):
    spec = importlib.util.spec_from_file_location('recorded_job', ROOT / 'tools/recorded_job.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    workspace = tmp_path / 'consumer'
    scripts = workspace / 'scripts'
    scripts.mkdir(parents=True)
    (scripts / 'Probe.py').write_text('print(1)')
    (scripts / 'secret.bin').write_bytes(b'not a script')
    runtime = tmp_path / 'service'
    staged = module.stage_scripts(scripts, workspace, runtime)
    assert (staged / 'Probe.py').read_text() == 'print(1)'
    assert not (staged / 'secret.bin').exists()
    assert 'Probe.py' in json.loads((staged / 'manifest.json').read_text())
    for invalid in (workspace, runtime, tmp_path):
        with pytest.raises(ValueError):
            module.stage_scripts(invalid, workspace, runtime)


def test_runtime_deployment_preserves_data_and_removes_legacy_software(tmp_path):
    import shutil
    runtime = tmp_path / 'installation'
    preserved = {
        '.local/config.json': 'private configuration',
        '.local/runtime/jobs.sqlite': 'retained jobs',
        'runtime/projects/project.gpr': 'private database',
        'runtime/scripts/script.py': 'consumer script',
        'docs/personal-notes.md': 'unmanaged notes',
    }
    for name, content in preserved.items():
        path = runtime / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
    # This fixture also existed in the broad 1.0.x private installation.
    fixture = runtime / 'fixtures/small.c'
    fixture.parent.mkdir()
    shutil.copyfile(ROOT / 'tests/fixtures/small.c', fixture)
    modified = runtime / 'docs/UPSTREAM_PLAN.md'
    modified.write_text('Locally changed file must survive migration')
    result = install(ROOT, runtime)
    assert not fixture.exists()
    assert result['preserved_modified_files'] == ['docs/UPSTREAM_PLAN.md']
    assert modified.exists()
    for name, content in preserved.items():
        assert (runtime / name).read_text() == content
    assert not any((runtime / name).exists() for name in ('engine', 'skills', 'scripts', 'target'))
    assert {p.name for p in (runtime / 'tools').iterdir()} == {'service.ps1', 'recorded_job.py'}
    manifest = json.loads((runtime / '.local/software.json').read_text())
    assert set(manifest['files']) == set(payload_files(ROOT))
    assert install(ROOT, runtime)['retired_files'] == 0


def test_runtime_deployment_rejects_manifest_escape_before_changes(tmp_path):
    runtime = tmp_path / 'installation'
    (runtime / '.local').mkdir(parents=True)
    state = runtime / '.local/software.json'
    state.write_text(json.dumps({'files': {'tools/../runtime/project.gpr': 'unused'}}))
    with pytest.raises(ValueError):
        install(ROOT, runtime)
    assert not (runtime / 'VERSION').exists()


def test_deployment_refuses_active_owner(tmp_path):
    import msvcrt
    import subprocess
    runtime = tmp_path / 'installation'
    state = runtime / '.local/runtime'
    state.mkdir(parents=True)
    (runtime / '.local/config.json').write_text('{}')
    with (state / 'supervisor.lock').open('w+b') as lock:
        lock.write(b'0')
        lock.flush()
        lock.seek(0)
        msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
        result = subprocess.run(['powershell', '-NoProfile', '-File',
                                 str(ROOT / 'scripts/deploy.ps1'), '-Root', str(runtime), '-Update'],
                                capture_output=True, text=True)
    assert result.returncode != 0
    assert 'Stop the shared service' in result.stderr
    assert not (runtime / 'VERSION').exists()
