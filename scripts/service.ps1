param([ValidateSet('start','status','stop')][string]$Action='status',
      [string]$Root=$(if($env:GHIDRA_SHARED_HOME){$env:GHIDRA_SHARED_HOME}else{Join-Path ([Environment]::GetFolderPath('UserProfile')) 'ghidra-shared'}))
$ErrorActionPreference='Stop'
$entry=Join-Path $Root 'tools/service.ps1'
if(!(Test-Path -LiteralPath $entry)){throw 'Shared Ghidra is not installed. Run scripts/deploy.ps1 first.'}
& $entry $Action
exit $LASTEXITCODE
