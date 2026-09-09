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
# Explicit software allowlist. Never copy source caches, credentials or projects.
foreach($folder in @('service','engine','tools','docs','scripts','skills')){
    Copy-Item -LiteralPath (Join-Path $source $folder) -Destination $destination -Recurse -Force -Exclude '__pycache__','*.pyc','*.class'
}
foreach($file in @('VERSION','LICENSE','README.md','requirements.txt','requirements.lock','toolchain.json','bridge_mcp_ghidra.py')){
    Copy-Item -LiteralPath (Join-Path $source $file) -Destination $destination -Force
}
& "$destination/tools/install.ps1" -Port $Port -Workers 4
if($LASTEXITCODE){throw 'Service installation failed.'}
$version=(Get-Content "$source/VERSION" -Raw).Trim()
@{version=$version;source='https://github.com/adiazpar/ghidra-mcp-parallel';installedAt=[DateTime]::UtcNow.ToString('o')} |
    ConvertTo-Json | Set-Content -Encoding ascii "$destination/.local/software.json"
Write-Output "Shared Ghidra $version installed at $destination. Start with scripts/service.ps1 start."
