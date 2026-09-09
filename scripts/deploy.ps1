param([string]$Root=$(Join-Path ([Environment]::GetFolderPath('UserProfile')) 'ghidra-shared'),
      [ValidateRange(1024,65535)][int]$Port=18766, [switch]$Update)
$ErrorActionPreference='Stop'
$source=(Resolve-Path "$PSScriptRoot/..").Path
$destination=[IO.Path]::GetFullPath($Root)
if($destination.TrimEnd('\') -eq $source.TrimEnd('\')){throw 'The private installation must be separate from plugin source.'}
if(Test-Path -LiteralPath $destination){
    if(!$Update){throw 'Installation exists. Stop the service and use -Update to replace software while preserving data.'}
    if(!(Test-Path -LiteralPath "$destination/.local/config.json")){throw 'Existing directory is not a shared service installation.'}
    $lockPath="$destination/.local/runtime/supervisor.lock"
    if(Test-Path -LiteralPath $lockPath){
        $guard=[IO.File]::Open($lockPath,[IO.FileMode]::Open,[IO.FileAccess]::ReadWrite,[IO.FileShare]::ReadWrite)
        try{$guard.Lock(0,1);$guard.Unlock(0,1)}catch{throw 'Stop the shared service before updating.'}finally{$guard.Dispose()}
    }
}
New-Item -ItemType Directory -Force -Path $destination | Out-Null
# Build from plugin source; install only the runtime payload at the destination.
& "$source/tools/install.ps1" -Root $destination -RuntimeOnly -Port $Port -Workers 4
if($LASTEXITCODE){throw 'Service installation failed.'}
$version=(Get-Content "$source/VERSION" -Raw).Trim()
Write-Output "Shared Ghidra $version installed at $destination. Start with scripts/service.ps1 start."
