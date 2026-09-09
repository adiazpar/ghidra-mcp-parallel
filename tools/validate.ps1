param([switch]$Benchmarks)
$ErrorActionPreference='Stop'
$root=Split-Path $PSScriptRoot -Parent
Push-Location $root
try {
    & "$root/tests/build_fixtures.ps1"
    & "$PSScriptRoot/build.ps1" -FixtureScripts
    & .venv/Scripts/python.exe -m tests.prepare
    if($LASTEXITCODE){throw 'Validation fixture setup failed'}
    & .venv/Scripts/python.exe -m pytest tests/test_live.py tests/test_supervisor.py tests/test_plugin.py -q --junitxml=.local/validation/junit.xml
    if($LASTEXITCODE){throw 'Validation failed'}
    if($Benchmarks) {
        & .venv/Scripts/python.exe -m tests.benchmarks.measure
        if($LASTEXITCODE){throw 'Measurement failed'}
        & .venv/Scripts/python.exe -m tests.benchmarks.mixed_measure
        if($LASTEXITCODE){throw 'Mixed measurement failed'}
        & .venv/Scripts/python.exe -m tests.benchmarks.compatibility
        if($LASTEXITCODE){throw 'Compatibility comparison failed'}
    }
} finally { Pop-Location }
