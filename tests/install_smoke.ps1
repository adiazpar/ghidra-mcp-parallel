param([Parameter(Mandatory=$true)][string]$Root)
$ErrorActionPreference='Stop'
$source=Split-Path $PSScriptRoot -Parent
$destination=[IO.Path]::GetFullPath($Root)
if(Test-Path -LiteralPath $destination){throw 'Installation smoke test requires a new disposable directory.'}
& "$source/scripts/deploy.ps1" -Root $destination -Port 18767
if($LASTEXITCODE){throw 'Fresh deployment failed'}
$configHash=(Get-FileHash "$destination/.local/config.json").Hash
& "$source/scripts/deploy.ps1" -Root $destination -Port 18767 -Update
if($LASTEXITCODE){throw 'Repeated deployment failed'}
if((Get-FileHash "$destination/.local/config.json").Hash -ne $configHash){throw 'Update changed private configuration'}
$started=$false
try {
    & "$source/scripts/service.ps1" start -Root $destination
    if($LASTEXITCODE){throw 'Runtime startup failed'}
    $started=$true
    Push-Location $destination
    try {
        & "$destination/.venv/Scripts/python.exe" -c @'
import json
from pathlib import Path
from service.client import Client
root=Path.cwd()
assert {p.name for p in root.iterdir()} == {'.local','.venv','service','tools','VERSION','LICENSE','bridge_mcp_ghidra.py'}
assert {p.name for p in (root/'tools').iterdir()} == {'service.ps1','recorded_job.py'}
c=Client()
s=c.call('session_open',label='installation smoke')['session']
try:
    health=c.call('service_health')
    assert health['state']=='ready' and health['workers']==4
    r=c.run(s,'capabilities',{})
    assert r['status']=='completed' and r['ghidra']=='12.1.3',r
finally:
    c.call('session_close',session=s)
print('Fresh and repeated deployment passed; minimal runtime starts and serves MCP')
'@
        if($LASTEXITCODE){throw 'Runtime smoke validation failed'}
    } finally { Pop-Location }
} finally {
    if($started){ & "$source/scripts/service.ps1" stop -Root $destination }
}
