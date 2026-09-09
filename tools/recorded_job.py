"""Recorded jobs and staged scripts through the installed shared MCP service."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from service.client import Client


def stage_scripts(directory, workspace, root=ROOT):
    directory, workspace, root = directory.resolve(), workspace.resolve(), root.resolve()
    if (not directory.is_relative_to(workspace) or directory == workspace or
            root.is_relative_to(directory) or directory.is_relative_to(root)):
        raise ValueError('Choose a workspace script subdirectory outside the service installation')
    destination = root / 'runtime/scripts' / uuid.uuid4().hex
    destination.mkdir(parents=True)
    manifest = {}
    for source in directory.rglob('*'):
        if '__pycache__' in source.parts or source.suffix not in ('.py', '.java', '.class', '.properties'):
            continue
        if not source.is_file() or not source.resolve().is_relative_to(directory):
            continue
        relative = source.relative_to(directory)
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        manifest[relative.as_posix()] = hashlib.sha256(target.read_bytes()).hexdigest()
    (destination / 'manifest.json').write_text(json.dumps(manifest, indent=2))
    return destination


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', nargs='?', default='programs')
    parser.add_argument('--workspace', type=Path, default=Path.cwd())
    parser.add_argument('--arguments', type=Path)
    parser.add_argument('--program')
    parser.add_argument('--function')
    parser.add_argument('--script', type=Path)
    parser.add_argument('--script-dir', type=Path)
    parser.add_argument('--script-arg', action='append', default=[])
    parser.add_argument('--analyze', action='store_true')
    parser.add_argument('--timeout', type=int, default=600)
    parser.add_argument('--evidence', type=Path)
    parser.add_argument('--log', type=Path)
    args = parser.parse_args()
    workspace = args.workspace.resolve()
    evidence = (args.evidence or workspace / 'logs/shared-ghidra' / (uuid.uuid4().hex + '.json')).resolve()
    if not evidence.is_relative_to(workspace) or (args.log and not args.log.resolve().is_relative_to(workspace)):
        raise ValueError('Evidence and log must remain inside the selected workspace')
    client = Client()
    session = client.call('session_open', label='recorded CLI job')['session']
    record = {'session': session}
    evidence.parent.mkdir(parents=True, exist_ok=True)

    def persist():
        evidence.write_text(json.dumps(record, indent=2), encoding='utf-8')

    try:
        arguments = json.loads(args.arguments.read_text()) if args.arguments else {}
        if args.program:
            arguments['program'] = args.program
        if args.function:
            arguments['function'] = args.function
        if args.script:
            if args.operation != 'script' or not args.program:
                raise ValueError('--script requires script operation and --program')
            source = args.script.resolve()
            directory = (args.script_dir or source.parent).resolve()
            relative = source.relative_to(directory)
            staged = stage_scripts(directory, workspace)
            if not (staged / relative).is_file():
                raise ValueError('Script was not staged')
            arguments.update(name=relative.as_posix(), paths=[staged.relative_to(ROOT).as_posix()],
                             args=args.script_arg, analyze=args.analyze)
            if 'expected_version' not in arguments:
                programs = client.run(session, 'programs', {})
                if programs['status'] != 'completed':
                    raise RuntimeError(programs.get('error', programs['status']))
                identity = next(p for p in programs['output']['loaded'] if p['id'] == args.program)
                arguments['expected_version'] = identity['version']
            record['script_manifest'] = str(staged / 'manifest.json')
        record.update(operation=args.operation, arguments=arguments)
        accepted = client.call('job_submit', session=session, operation=args.operation,
                               arguments=arguments, timeout_seconds=args.timeout)
        record['accepted'] = accepted
        persist()
        deadline = time.monotonic() + args.timeout + 90
        while time.monotonic() < deadline:
            result = client.call('job_result', session=session, job=accepted['id'])
            if result['status'] in ('completed', 'failed', 'cancelled', 'timed_out'):
                break
            time.sleep(.1)
        else:
            raise TimeoutError('Service did not report terminal status within cancellation/recovery grace')
        record['result'] = result
        persist()
        if args.log:
            output = result.get('output', {})
            body = (output.get('stdout', '') + output.get('stderr', '') if isinstance(output, dict)
                    else json.dumps(output))
            body += '\n[shared-ghidra] status=' + result['status'] + ' job=' + accepted['id'] + '\n'
            body += 'Evidence: ' + str(evidence) + '\n'
            if result.get('error'):
                body += result['error'] + '\n'
            args.log.parent.mkdir(parents=True, exist_ok=True)
            args.log.write_text(body, encoding='utf-8')
            print(body)
        else:
            print(json.dumps(result, indent=2))
        print('Evidence: ' + str(evidence), file=sys.stderr)
        return 0 if result['status'] == 'completed' else 124 if result['status'] == 'timed_out' else 1
    finally:
        client.call('session_close', session=session)


if __name__ == '__main__':
    raise SystemExit(main())
