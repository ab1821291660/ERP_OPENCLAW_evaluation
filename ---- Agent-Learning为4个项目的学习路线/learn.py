"""Clone pinned learning repositories and run their offline demos and checks."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
REPOS = ROOT / 'repos'


def invoke(command, cwd=ROOT, timeout=180):
    result = subprocess.run(command, cwd=cwd, text=True, encoding='utf-8', errors='replace', capture_output=True,
                            env=dict(os.environ, PYTHONIOENCODING='utf-8', GIT_TERMINAL_PROMPT='0'), timeout=timeout)
    return result


def git(*args):
    result = invoke(['git', *args])
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or 'git failed')
    return result.stdout.strip()


def entries():
    projects = json.loads((ROOT / 'projects.json').read_text(encoding='utf-8'))['projects']
    for project in projects:
        if not re.fullmatch(r'[A-Za-z0-9_-]+', project['directory']):
            raise ValueError('Invalid repository directory')
        if not re.fullmatch(r'[0-9a-f]{40}', project['commit']):
            raise ValueError('Each project must have a pinned full commit SHA')
        if project['url'] != 'https://github.com/ooo1208/' + project['directory'] + '.git':
            raise ValueError('Unexpected repository URL')
        if (ROOT / '.gitmodules').exists():
            relative = 'repos/' + project['directory']
            registered_url = git('config', '--file', str(ROOT / '.gitmodules'), '--get', 'submodule.' + relative + '.url')
            indexed = git('ls-files', '--stage', '--', relative).split()
            if registered_url != project['url'] or indexed[:2] != ['160000', project['commit']]:
                raise ValueError(f'{relative}: submodule and projects.json revisions must agree')
    return projects


def clone(project):
    target = REPOS / project['directory']
    if (target / '.git').exists():
        origin = git('-C', str(target), 'remote', 'get-url', 'origin')
        head = git('-C', str(target), 'rev-parse', 'HEAD')
        if origin != project['url'] or head != project['commit']:
            raise RuntimeError(f'{target.name}: existing checkout differs from manifest; left untouched. Preserve your changes and use another clone directory.')
        print(f'{target.name}: matching checkout already present; left untouched')
        return
    if target.exists() and (not target.is_dir() or any(target.iterdir())):
        raise RuntimeError(f'{target.name} contains files and is not a Git checkout; left untouched')
    if (ROOT / '.gitmodules').exists():
        git('submodule', 'update', '--init', '--', 'repos/' + project['directory'])
        print(f'{target.name}: submodule initialized at {project["commit"][:12]}')
        return
    REPOS.mkdir(exist_ok=True)
    git('clone', '--no-checkout', project['url'], str(target))
    git('-C', str(target), 'switch', '-c', 'study', project['commit'])
    print(f'{target.name}: study branch at {project["commit"][:12]}')


def run_check(label, directory, args, expected=0, executable=None):
    command = [str(executable or sys.executable), '-X', 'utf8', *args]
    print(f'\n[{label}]', flush=True)
    try:
        result = invoke(command, REPOS / directory)
        output = result.stdout + result.stderr
        print(output, end='' if output.endswith('\n') else '\n')
        count = re.search(r'Ran (\d+) tests?', output)
        return {'label': label, 'exit_code': result.returncode, 'expected_exit_code': expected,
                'passed': result.returncode == expected, 'tests': int(count.group(1)) if count else 0, 'output': output}
    except (OSError, subprocess.TimeoutExpired) as exc:
        print(f'Failed: {exc}')
        return {'label': label, 'passed': False, 'tests': 0, 'error': str(exc)}


def main():
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description=__doc__)
    subs = parser.add_subparsers(dest='command', required=True)
    subs.add_parser('list')
    clone_parser = subs.add_parser('clone')
    clone_parser.add_argument('--with-erp', action='store_true')
    demo = subs.add_parser('demo')
    demo.add_argument('project', choices=['all', 'ctrip', 'rag', 'sql'], default='all', nargs='?')
    verify = subs.add_parser('verify')
    verify.add_argument('--include-erp', action='store_true')
    args = parser.parse_args()
    projects = entries()
    if args.command == 'list':
        for p in projects:
            print(f'{p["id"]:6} {p["url"]} @ {p["commit"][:12]}')
        return 0
    if args.command == 'clone':
        for p in projects:
            if p['id'] != 'erp' or args.with_erp:
                clone(p)
        return 0
    results = []
    revisions = []
    for p in projects:
        if p['id'] == 'erp':
            continue
        if args.command == 'demo' and args.project not in ('all', p['id']):
            continue
        target = REPOS / p['directory']
        if not (target / '.git').exists():
            raise RuntimeError(f'{p["directory"]} is missing; run python learn.py clone first')
        revisions.append({'project': p['id'], 'expected': p['commit'], 'actual': git('-C', str(target), 'rev-parse', 'HEAD'),
                          'modified': bool(git('-C', str(target), 'status', '--porcelain'))})
        results.append(run_check(p['id'] + ' demo', p['directory'], p['demo']))
        if args.command == 'verify':
            results.append(run_check(p['id'] + ' tests', p['directory'], p['tests']))
    if args.command == 'verify' and args.include_erp:
        directory = 'ERP_OPENCLAW'
        python = REPOS / directory / '.venv' / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
        if not python.exists():
            results.append({'label': 'ERP environment', 'passed': False, 'tests': 0,
                            'error': 'Run clone --with-erp, then install ERP dependencies using its README.'})
        else:
            for variant, expected in [('baseline', 0), ('regressed', 1)]:
                arguments = ['-m', 'asu_eval.gate', '--dataset', 'evals/golden.synthetic.json', '--predictions',
                             f'evals/predictions.{variant}.json', '--baseline', 'evals/baseline.synthetic.json']
                results.append(run_check('ERP eval ' + variant, directory, arguments, expected, python))
    passed = bool(results) and all(r['passed'] for r in results)
    count = sum(r['tests'] for r in results)
    report = {'checked_at_utc': datetime.now(timezone.utc).isoformat(), 'passed': passed, 'tests': count,
              'scope': 'offline synthetic demos and tests', 'revisions': revisions, 'checks': results}
    local = ROOT / '.local'
    local.mkdir(exist_ok=True)
    (local / ('last-verification.json' if args.command == 'verify' else 'last-demo.json')).write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'\nPassed {sum(r["passed"] for r in results)}/{len(results)} checks; {count} tests. Offline synthetic scope only.')
    return 0 if passed else 1


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (RuntimeError, ValueError, OSError, subprocess.TimeoutExpired) as error:
        print(f'Error: {error}', file=sys.stderr)
        raise SystemExit(1)
