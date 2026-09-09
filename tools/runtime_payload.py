"""Install runtime files and retire unchanged files from older deployments."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil


MANAGED_DIRS = ('service', 'tools', 'engine', 'docs', 'scripts', 'skills',
                'target', 'tests', 'fixtures', 'examples')
MANAGED_FILES = ('VERSION', 'LICENSE', 'README.md', 'requirements.txt',
                 'requirements.lock', 'toolchain.json', 'pytest.ini', 'bridge_mcp_ghidra.py')


def digest(path):
    # Git checkouts may use CRLF while packaged source uses LF.
    return hashlib.sha256(path.read_bytes().replace(b'\r\n', b'\n')).hexdigest()


def safe_path(root, relative):
    relative = Path(relative)
    if relative.is_absolute() or '..' in relative.parts or relative.drive:
        raise ValueError(f'Invalid relative path: {relative}')
    path = root / relative
    if not path.resolve().is_relative_to(root.resolve()) or path.resolve() == root.resolve():
        raise ValueError(f'Path outside installation: {relative}')
    for part in (path, *path.parents):
        if part == root:
            break
        if part.is_symlink() or part.is_junction():
            raise ValueError(f'Linked installation path: {relative}')
    return path


def payload_files(source):
    files = [p.relative_to(source).as_posix() for p in (source / 'service').rglob('*.py')
             if '__pycache__' not in p.parts]
    return sorted(files + ['tools/service.ps1', 'tools/recorded_job.py',
                           'bridge_mcp_ghidra.py', 'LICENSE', 'VERSION'])


def install(source, destination):
    source, destination = source.resolve(), destination.resolve()
    if source == destination or source.is_relative_to(destination):
        raise ValueError('Runtime installation must be separate from source')
    wanted = payload_files(source)
    legacy = json.loads((source / 'tools/legacy-runtime.json').read_text())
    state = safe_path(destination, '.local/software.json')
    previous = json.loads(state.read_text()) if state.exists() else {}
    for relative, checksum in previous.get('files', {}).items():
        if Path(relative).parts[0] not in MANAGED_DIRS and relative not in MANAGED_FILES:
            raise ValueError(f'Invalid managed file: {relative}')
        legacy.setdefault(relative, []).append(checksum)
    removals, preserved = [], []
    for relative, checksums in legacy.items():
        path = safe_path(destination, relative)
        if relative not in wanted and path.is_file():
            if digest(path) in checksums:
                removals.append(path)
            else:
                preserved.append(relative)
    # Bytecode and javac output are disposable, confined to software directories.
    for folder in MANAGED_DIRS:
        base = safe_path(destination, folder)
        if not base.exists():
            continue
        for path in base.rglob('*'):
            path = safe_path(destination, path.relative_to(destination))
            if path.is_file() and ('__pycache__' in path.parts or
                    (folder == 'target' and (path.suffix in ('.class', '.jar') or path.name == 'javac.args'))):
                removals.append(path)
    build = safe_path(destination, '.local/install-build')
    if build.exists():
        for path in build.rglob('*'):
            path = safe_path(destination, path.relative_to(destination))
            if path.is_file() and (path.suffix in ('.class', '.jar') or path.name == 'javac.args'):
                removals.append(path)
    for relative in wanted:
        safe_path(source, relative)
        safe_path(destination, relative)
    for relative in wanted:
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source / relative, target)
    for path in set(removals):
        path.unlink()
    for folder in (*MANAGED_DIRS, '.local/install-build'):
        base = destination / folder
        if base.is_dir():
            directories = [p for p in base.rglob('*') if p.is_dir()] + [base]
            for path in sorted(directories, key=lambda p: len(p.parts), reverse=True):
                if not any(path.iterdir()):
                    path.rmdir()
    version = (source / 'VERSION').read_text().strip()
    state.parent.mkdir(parents=True, exist_ok=True)
    state.write_text(json.dumps({
        'version': version, 'source': 'https://github.com/adiazpar/ghidra-mcp-parallel',
        'installedAt': datetime.now(timezone.utc).isoformat(),
        'files': {name: digest(destination / name) for name in wanted},
    }, indent=2))
    return {'version': version, 'runtime_files': len(wanted),
            'retired_files': len(set(removals)), 'preserved_modified_files': preserved}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('destination', type=Path)
    args = parser.parse_args()
    print(json.dumps(install(Path(__file__).resolve().parents[1], args.destination), indent=2))
