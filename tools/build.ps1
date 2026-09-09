param([switch]$Upstream,[switch]$FixtureScripts)
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
$ghidra = Join-Path $root '.local/ghidra_12.1.3_PUBLIC'
if (!(Test-Path "$ghidra/Ghidra/application.properties")) { throw 'Run tools/install.ps1 first' }
$javac = (Get-Command javac).Source
if ((& $javac -version 2>&1) -notmatch '21\.0\.11') { throw 'Pinned JDK 21.0.11 required' }
$jars = Get-ChildItem "$ghidra/Ghidra" -Recurse -Filter *.jar | ForEach-Object FullName
$classes = Join-Path $root 'target/service-classes'
if($Upstream) { $classes = Join-Path $root 'target/upstream-classes' }
if($FixtureScripts) { $classes = Join-Path $root '.local/fixture-classes' }
New-Item -ItemType Directory -Force $classes | Out-Null
$sources = @(Get-ChildItem "$root/engine/src/main/java" -Recurse -Filter *.java | ForEach-Object FullName)
if($Upstream) { $sources = @(Get-ChildItem "$root/src/main/java" -Recurse -Filter *.java | ForEach-Object FullName) }
if($FixtureScripts) { $sources = @(Get-ChildItem "$root/fixtures/scripts" -Filter *.java | ForEach-Object FullName) }
$arguments = @('-proc:none','-encoding','UTF-8','-cp',('"'+($jars -join ';')+'"'),'-d',('"'+$classes+'"')) + ($sources | ForEach-Object {'"'+$_+'"'})
$argfile = Join-Path $root 'target/javac.args'
($arguments -replace '\\','/') | Set-Content -Encoding utf8 $argfile
# PowerShell 5.1 adds a BOM that javac does not accept.
[IO.File]::WriteAllLines($argfile, ($arguments -replace '\\','/'), (New-Object Text.UTF8Encoding($false)))
& $javac "@$argfile"
if($LASTEXITCODE) { throw 'Java compilation failed' }
if($FixtureScripts) { return }
& (Join-Path (Split-Path $javac) 'jar.exe') --create --file "$root/target/shared-service.jar" -C $classes .
if($LASTEXITCODE) { throw 'Jar creation failed' }
