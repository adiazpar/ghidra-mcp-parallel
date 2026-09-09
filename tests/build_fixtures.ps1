$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
$vswhere = "${env:ProgramFiles(x86)}/Microsoft Visual Studio/Installer/vswhere.exe"
$vs = & $vswhere -latest -products '*' -property installationPath
$cl = Join-Path $vs 'VC/Tools/MSVC/14.44.35207/bin/Hostx64/x64/cl.exe'
if (!(Test-Path $cl)) { throw 'MSVC 14.44.35207 x64 compiler required' }
New-Item -ItemType Directory -Force "$root/.local/fixtures" | Out-Null
Push-Location "$root/.local/fixtures"
try {
    & $cl /nologo /O1 /GS- /Zl /Fo:small.obj "$root/tests/fixtures/small.c" /link /nodefaultlib /entry:entry /subsystem:console /out:small.exe
    if($LASTEXITCODE) { throw 'Fixture compilation failed' }
    & "$root/.venv/Scripts/python.exe" "$root/tests/fixtures/generate.py"
    & $cl /nologo /O1 /GS- /Zl /Fo:large.obj large.c /link /nodefaultlib /entry:entry /subsystem:console /out:large.exe
    if($LASTEXITCODE) { throw 'Large fixture compilation failed' }
} finally { Pop-Location }
