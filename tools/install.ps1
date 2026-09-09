param([ValidateRange(1024,65535)][int]$Port=18765,[ValidateRange(1,4)][int]$Workers=4,[switch]$Comparison)
$ErrorActionPreference='Stop'
$root=Split-Path $PSScriptRoot -Parent
if(Test-Path "$root/.local/runtime/supervisor.lock") {
    $lockStream=[IO.File]::Open("$root/.local/runtime/supervisor.lock",[IO.FileMode]::Open,[IO.FileAccess]::ReadWrite,[IO.FileShare]::ReadWrite)
    try { $lockStream.Lock(0,1); $lockStream.Unlock(0,1) }
    catch { throw 'Stop the local service before installing or updating its engine' }
    finally { $lockStream.Dispose() }
}
$pin=Get-Content "$root/toolchain.json" -Raw | ConvertFrom-Json
if($Port -eq 8080){throw 'Port 8080 is reserved for the existing setup'}
New-Item -ItemType Directory -Force "$root/.local/downloads","$root/.local/runtime" | Out-Null
$archive="$root/.local/downloads/ghidra.zip"
if(!(Test-Path "$root/.local/ghidra_12.1.3_PUBLIC")) {
    if(!(Test-Path $archive)){ & curl.exe -L --fail --output $archive $pin.ghidra_url; if($LASTEXITCODE){throw 'Download failed'} }
    if((Get-FileHash $archive -Algorithm SHA256).Hash.ToLower() -ne $pin.ghidra_sha256){throw 'Ghidra SHA-256 mismatch'}
    & python -c "import zipfile; zipfile.ZipFile(r'$archive').extractall(r'$root/.local')"
    if($LASTEXITCODE){throw 'Extraction failed'}
}
if(!(Select-String -LiteralPath "$root/.local/ghidra_12.1.3_PUBLIC/Ghidra/application.properties" -Pattern '^application.version=12\.1\.3$')){throw 'Installed Ghidra version differs from the pinned toolchain'}
if($Comparison) {
    $comparisonArchive="$root/.local/downloads/ghidra-11.3.2.zip"
    if(!(Test-Path $comparisonArchive)){ & curl.exe -L --fail --output $comparisonArchive $pin.comparison_ghidra_url; if($LASTEXITCODE){throw 'Comparison download failed'} }
    if((Get-FileHash $comparisonArchive -Algorithm SHA256).Hash.ToLower() -ne $pin.comparison_ghidra_sha256){throw 'Comparison archive SHA-256 mismatch'}
    if(!(Test-Path "$root/.local/ghidra_11.3.2_PUBLIC")) {
        & python -c "import zipfile; zipfile.ZipFile(r'$comparisonArchive').extractall(r'$root/.local')"
        if($LASTEXITCODE){throw 'Comparison archive extraction failed'}
    }
}
$env:UV_CACHE_DIR="$root/.local/uv-cache"
$env:UV_PYTHON_INSTALL_DIR="$root/.local/python"
if(!(Test-Path "$root/.venv")){ & uv venv "$root/.venv" --python 3.12.9; if($LASTEXITCODE){throw 'venv failed'} }
& uv pip sync --python "$root/.venv/Scripts/python.exe" "$root/requirements.lock"
if($LASTEXITCODE){throw 'Dependency installation failed'}
& "$root/.venv/Scripts/python.exe" -c "import zipfile; from pathlib import Path; g=Path(r'$root/.local/ghidra_12.1.3_PUBLIC'); zipfile.ZipFile(next((g/'Extensions/Ghidra').glob('*Jython.zip'))).extractall(g/'Ghidra/Extensions')"
if($LASTEXITCODE){throw 'Bundled Jython extension installation failed'}
if(!(Test-Path "$root/.local/config.json")) {
    $bytes=New-Object byte[] 32; $rng=[Security.Cryptography.RandomNumberGenerator]::Create();$rng.GetBytes($bytes);$rng.Dispose()
    $config=@{host='127.0.0.1';port=$Port;workers=$Workers;java=(Get-Command java).Source;ghidra='.local/ghidra_12.1.3_PUBLIC';token=[Convert]::ToBase64String($bytes);heap_mb=4096;memory_mb=6144;max_programs=2;queue_limit=64;per_session_jobs=16;max_sessions=128;retained_jobs=256;output_bytes=1048576;cache_entries=64;session_idle_seconds=1800;cancel_grace_seconds=10}
    $config | ConvertTo-Json | Set-Content -Encoding ascii "$root/.local/config.json"
    & icacls.exe "$root/.local/config.json" /inheritance:r /grant:r "$($env:USERNAME):(F)" | Out-Null
    if($LASTEXITCODE){throw 'Unable to restrict config permissions'}
}
& "$PSScriptRoot/build.ps1"
$extension="$root/.local/ghidra_12.1.3_PUBLIC/Ghidra/Extensions/SharedService"
New-Item -ItemType Directory -Force "$extension/lib" | Out-Null
Copy-Item -LiteralPath "$root/target/shared-service.jar" -Destination "$extension/lib/shared-service.jar"
'MODULE FILE LICENSE: lib/shared-service.jar Apache License 2.0' | Set-Content -Encoding ascii "$extension/Module.manifest"
@('name=SharedService','description=Persistent shared program engine','author=','createdOn=2026-09-08','version=12.1.3') | Set-Content -Encoding ascii "$extension/extension.properties"
Write-Output 'Isolated service installed. Run tools/service.ps1 start.'
