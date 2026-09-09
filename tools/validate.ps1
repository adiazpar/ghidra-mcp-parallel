param([switch]$Benchmarks)
$ErrorActionPreference='Stop'
$root=Split-Path $PSScriptRoot -Parent
Push-Location $root
try {
    & "$PSScriptRoot/fixtures.ps1"
    & "$PSScriptRoot/build.ps1" -FixtureScripts
    & .venv/Scripts/python.exe -m tools.prepare_validation
    if($LASTEXITCODE){throw 'Validation fixture setup failed'}
    & .venv/Scripts/python.exe -m pytest tests/test_live.py tests/test_supervisor.py tests/test_plugin.py -q --junitxml=.local/validation/junit.xml
    if($LASTEXITCODE){throw 'Validation failed'}
    if($Benchmarks) {
        & .venv/Scripts/python.exe -m tools.measure
        if($LASTEXITCODE){throw 'Measurement failed'}
        & .venv/Scripts/python.exe -m tools.mixed_measure
        if($LASTEXITCODE){throw 'Mixed measurement failed'}
        & .venv/Scripts/python.exe -m tools.compatibility
        if($LASTEXITCODE){throw 'Compatibility comparison failed'}
    }
} finally { Pop-Location }
