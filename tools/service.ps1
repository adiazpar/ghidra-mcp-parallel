param([ValidateSet('start','status','stop')][string]$Action='status')
$ErrorActionPreference='Stop'
$root=Split-Path $PSScriptRoot -Parent
$python=Join-Path $root '.venv/Scripts/python.exe'
Push-Location $root
try {
    if($Action -eq 'start') {
        $runtime=Join-Path $root '.local/runtime'
        New-Item -ItemType Directory -Force $runtime | Out-Null
        $config=Get-Content "$root/.local/config.json" -Raw | ConvertFrom-Json
        # Fail if the selected port is already in use; never stop a process to free it.
        $listener=New-Object Net.Sockets.TcpListener([Net.IPAddress]::Loopback,$config.port)
        $listener.Start(); $listener.Stop()
        $proc=Start-Process -FilePath $python -ArgumentList '-m','service.server' -WorkingDirectory $root -WindowStyle Hidden -PassThru -RedirectStandardOutput "$runtime/supervisor.out.log" -RedirectStandardError "$runtime/supervisor.err.log"
        $proc.Id | Set-Content "$runtime/supervisor.pid"
        & $python -m service.control
        if($LASTEXITCODE){throw 'Service startup failed; inspect .local/runtime logs'}
    } else {
        if($Action -eq 'stop') {
            & $python -c "from service.client import Client; import psutil,json; c=Client(); h=c.call('service_health'); p=psutil.Process(h['supervisor_pid']); print(json.dumps(c.call('service_stop'))); p.wait(timeout=30)"
        } else {
            & $python -c "from service.client import Client; import json; print(json.dumps(Client().call('service_health'), indent=2))"
        }
        if($LASTEXITCODE){throw 'Service command failed; inspect .local/runtime logs'}
    }
} finally { Pop-Location }
