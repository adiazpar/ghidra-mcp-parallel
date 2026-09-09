$ErrorActionPreference='Stop'
$root=Split-Path $PSScriptRoot -Parent
& "$PSScriptRoot/build.ps1"
Push-Location $root
try {
& "$root/.venv/Scripts/python.exe" -c @'
import hashlib, zipfile
from pathlib import Path
root=Path.cwd()
out=root/'dist'
out.mkdir(exist_ok=True)
files=[]
for folder in ('service','engine','tools','tests','docs','examples','scripts','skills','.codex-plugin','.claude-plugin','.agents'):
    files.extend(p for p in (root/folder).rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.suffix not in ('.pyc','.class'))
files.extend(root/name for name in ('VERSION','CHANGELOG.md','.mcp.json','README.md','LICENSE','requirements.txt','requirements.lock','toolchain.json','pytest.ini','bridge_mcp_ghidra.py','target/shared-service.jar'))
archive=out/'shared-ghidra-service.zip'
with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
    for p in sorted(files):
        relative=p.relative_to(root).as_posix()
        assert not any(part in ('.local','.venv','runtime') for part in p.relative_to(root).parts)
        z.write(p,relative)
digest=hashlib.file_digest(archive.open('rb'),'sha256').hexdigest()
(out/'SHA256SUMS').write_text(digest+'  '+archive.name+'\n')
print(str(archive.relative_to(root)))
print('sha256 '+digest)
'@
if($LASTEXITCODE){throw 'Packaging failed'}
} finally { Pop-Location }
