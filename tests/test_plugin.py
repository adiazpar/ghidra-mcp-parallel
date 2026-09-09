"""Distribution contracts and the external-workspace script staging boundary."""
import importlib.util
import json
from pathlib import Path
import pytest

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
