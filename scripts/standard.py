"""Offline, revision-bound rendering. Git object hashes authenticate embedded source."""
import base64
import difflib
import fnmatch
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess

CANONICAL = 'sshickles/repo-standard'
LOCK = '.repo-standard-source.json'
SECTIONS = ['Purpose and architecture', 'Commands and tool versions', 'Configuration ownership',
            'Local runtime setup', 'Verification', 'Deployment and recovery', 'Approved exceptions']
FILES = ['policy/policy.md', 'policy/repository.md', 'policy/t3-actions.json', 'scripts/t3_actions.py', 'AGENTS.md', 'CLAUDE.md',
         'ruleset.json', 'greptile.json', '.coderabbit.yaml', '.claude/settings.json',
         'docs/agents/review-checklist.md', 'docs/setup.md', 'docs/halo.md',
         'docs/t3-compatibility.md', '.githooks/pre-push',
         '.github/workflows/ci.yml', '.github/workflows/policy-audit.yml',
         'apply-ruleset.sh', 'scripts/new-repo', 'scripts/lint-shell', 'scripts/setup', 'scripts/check', 'scripts/test', 'scripts/review',
         'scripts/commands.py', 'scripts/development.py', 'scripts/pre_push.py',
         'scripts/repository.py', 'scripts/standard.py', 'scripts/halo.py',
         'scripts/worktree.py', 'scripts/wt.sh', 'scripts/install-hooks.mjs']
EXECUTABLES = ['scripts/lint-shell', 'scripts/new-repo', 'apply-ruleset.sh', 'scripts/setup', 'scripts/check', 'scripts/test', 'scripts/review', '.githooks/pre-push', 'scripts/wt.sh']

def runtime_files(output):
    return [name for name in output
            if (name.startswith('scripts/') and name.endswith(('.py', '.mjs'))) or name == 't3.json']


def git(source, *args):
    return subprocess.check_output(['git', *args], cwd=source, stderr=subprocess.DEVNULL)


def object_id(kind, data):
    return hashlib.sha1(kind.encode() + b' ' + str(len(data)).encode() + b'\0' + data).hexdigest()


def tree_entries(data):
    entries = {}
    while data:
        header, data = data.split(b'\0', 1)
        mode, name = header.decode().split(' ', 1)
        entries[name] = (mode, data[:20].hex())
        data = data[20:]
    return entries


def snapshot(source, revision):
    revision = git(source, 'rev-parse', '--verify', revision + '^{commit}').decode().strip()
    commit = git(source, 'cat-file', 'commit', revision)
    trees = {}
    files = {}
    root = commit.splitlines()[0].decode().removeprefix('tree ')
    for name in FILES:
        oid = root
        parts = name.split('/')
        for part in parts:
            if oid not in trees:
                trees[oid] = base64.b64encode(git(source, 'cat-file', 'tree', oid)).decode()
            mode, oid = tree_entries(base64.b64decode(trees[oid]))[part]
        if mode not in ('100644', '100755'):
            raise ValueError(f'Canonical source must be a regular file: {name}')
        files[name] = git(source, 'cat-file', 'blob', oid).decode()
    return {'repository': CANONICAL, 'revision': revision,
            'commit': base64.b64encode(commit).decode(), 'trees': trees, 'files': files}


def verify_snapshot(data):
    if data['repository'] != CANONICAL or not re.fullmatch('[0-9a-f]{40}', data['revision']):
        raise ValueError('Invalid canonical identity or revision')
    commit = base64.b64decode(data['commit'], validate=True)
    if object_id('commit', commit) != data['revision']:
        raise ValueError('Canonical commit proof does not match recorded revision')
    root = commit.splitlines()[0].decode().removeprefix('tree ')
    for name in data['files']:
        if Path(name).is_absolute() or '..' in Path(name).parts:
            raise ValueError('Invalid canonical file path')
        oid = root
        for part in name.split('/'):
            tree = base64.b64decode(data['trees'][oid], validate=True)
            if object_id('tree', tree) != oid:
                raise ValueError('Canonical tree proof mismatch')
            mode, oid = tree_entries(tree)[part]
        if mode not in ('100644', '100755') or object_id('blob', data['files'][name].encode()) != oid:
            raise ValueError(f'Canonical source proof mismatch: {name}')
    return data['files']


def json_text(data):
    return json.dumps(data, indent=2) + '\n'


def rules(config, files):
    data = json.loads(files['ruleset.json'])
    if not config['integrations']['greptile']:
        raise ValueError('Greptile is required; missing integration blocks rollout')
    checks = next(r for r in data['rules'] if r['type'] == 'required_status_checks')
    checks['parameters']['required_status_checks'] = config['ciChecks'] + [
        {'context': 'Greptile Review', 'integration_id': 867647}]
    return data


def render(data, config):
    files = verify_snapshot(data)
    body = files['policy/policy.md']
    digest = hashlib.sha256(body.encode()).hexdigest()
    output = {name: value for name, value in files.items() if not name.startswith('policy/')}
    output['docs/agents/policy.md'] = (
        '<!-- Generated. Do not edit. -->\n'
        f'Canonical repository: {CANONICAL}\n'
        f'Canonical revision: {data["revision"]}\n'
        'Canonical source: policy/policy.md\n'
        f'SHA-256: {digest}\n\n' + body)
    output[LOCK] = json_text(data)
    output['ruleset.json'] = json_text(rules(config, files))
    greptile = json.loads(files['greptile.json'])
    greptile['autoApprove']['filters']['includeRepositories'] = [config['repository']]
    output['greptile.json'] = json_text(greptile)
    settings = json.loads(files['.claude/settings.json'])
    settings['permissions']['deny'] = [re.sub(r'\bmain\b', lambda _: config['git']['baseBranch'], s)
                                       for s in settings['permissions']['deny']]
    output['.claude/settings.json'] = json_text(settings)
    from t3_actions import definitions, merge
    canonical = definitions(files)
    if canonical:
        output['t3.json'] = json_text(merge({}, canonical))
    return output


def validate(path, *, repair_missing_runtime=False):
    from development import read_config
    path = Path(path).resolve()
    config = read_config(path / '.repo-standard.json')
    data = json.loads((path / LOCK).read_text())
    expected = render(data, config)
    for name in [*expected, 'docs/agents/repository.md']:
        target_path(path, name)
    required_runtime = runtime_files(expected)
    for name in required_runtime:
        if not (path / name).is_file() and not repair_missing_runtime:
            raise ValueError(f'Required runtime file missing: {name}')
    from t3_actions import definitions, validate as validate_actions
    canonical = definitions(verify_snapshot(data))
    t3 = target_path(path, 't3.json')
    if canonical and not (repair_missing_runtime and not t3.exists()):
        validate_actions(json.loads(t3.read_text()), canonical)
    if (path / 'docs/agents/policy.md').read_text() != expected['docs/agents/policy.md']:
        raise ValueError('Generated policy drift from recorded canonical revision')
    # Local configuration is checked separately from shared policy content.
    for name in ('ruleset.json', 'greptile.json'):
        if json.loads((path / name).read_text()) != json.loads(expected[name]):
            raise ValueError(f'Configuration drift: {name}')
    actual_settings = json.loads((path / '.claude/settings.json').read_text())
    required_settings = json.loads(expected['.claude/settings.json'])
    for kind in ('allow', 'deny'):
        if not set(required_settings['permissions'][kind]).issubset(actual_settings.get('permissions', {}).get(kind, [])):
            raise ValueError('Configuration drift: .claude/settings.json permissions')
    for rule in actual_settings['permissions']['deny']:
        if blocks_native_merge(rule):
            raise ValueError('Permission denial shadows native auto-merge')
    if (path / '.coderabbit.yaml').read_text() != expected['.coderabbit.yaml']:
        raise ValueError('Configuration drift: .coderabbit.yaml')
    entry = (path / 'AGENTS.md').read_text()
    if any(link not in entry for link in ('docs/agents/policy.md', 'docs/agents/repository.md')):
        raise ValueError('AGENTS.md must link both policy and repository instructions')
    headings = re.findall(r'^## (.+)$', (path / 'docs/agents/repository.md').read_text(), re.M)
    if headings != SECTIONS:
        raise ValueError('repository.md must have exactly the seven required sections in order')
    if (path / 'CLAUDE.md').read_text().strip() != '@AGENTS.md':
        raise ValueError('CLAUDE.md must be a thin adapter to AGENTS.md')
    for name in EXECUTABLES:
        if not (path / name).is_file() or not os.access(path / name, os.X_OK):
            raise ValueError(f'Required executable missing: {name}')
    for name in ('scripts/setup', 'scripts/check', 'scripts/test', 'scripts/review',
                 'scripts/commands.py', 'scripts/pre_push.py', '.githooks/pre-push'):
        if repair_missing_runtime and name in required_runtime and not (path / name).exists():
            continue
        if (path / name).read_text() != expected[name]:
            raise ValueError(f'Command or hook drift: {name}')
    from pre_push import repository_checks
    repository_checks(path)
    hooks = subprocess.run(['git', 'config', '--local', '--get', 'core.hooksPath'], cwd=path, capture_output=True, text=True)
    if hooks.stdout.strip() != '.githooks':
        raise ValueError('Hook installation missing: run ./scripts/setup')
    print(f'Policy and required structure valid at {data["revision"]}')
    return data


def blocks_native_merge(rule):
    if rule == 'Bash':
        return True
    if not rule.startswith('Bash('):
        return False
    pattern = rule[5:-1].replace(':*', ' *')
    return any(fnmatch.fnmatchcase(cmd, pattern) for cmd in (
        'gh pr merge 123 --auto --squash', 'gh pr merge 123 --disable-auto'))


def merge_settings(existing, desired, previous=None):
    merged = json.loads(existing)
    wanted = json.loads(desired)
    old = json.loads(previous) if previous else {'permissions': {}}
    permissions = merged.setdefault('permissions', {})
    for kind in ('allow', 'deny'):
        retained = [rule for rule in permissions.get(kind, [])
                    if rule not in old.get('permissions', {}).get(kind, [])]
        if kind == 'deny':
            retained = [rule for rule in retained if not blocks_native_merge(rule)
                        and not any(value in rule for value in ('vercel --prod', 'convex deploy', '--run-prod'))]
        permissions[kind] = list(dict.fromkeys(retained + wanted['permissions'][kind]))
    return json_text(merged)


def target_path(path, name):
    if Path(name).is_absolute() or '..' in Path(name).parts:
        raise ValueError('Managed paths must stay in the target checkout')
    target = path / name
    for parent in (target, *target.parents):
        if parent == path:
            break
        if parent.is_symlink():
            raise ValueError(f'Managed path is a symlink; preserve and integrate manually: {name}')
    return target


def plan(path, data, config):
    output = render(data, config)
    output['.repo-standard.json'] = json_text(config)
    from t3_actions import definitions, merge
    canonical = definitions(data['files'])
    t3 = target_path(path, 't3.json')
    if canonical and t3.exists():
        output['t3.json'] = json_text(merge(json.loads(t3.read_text()), canonical))
    settings = path / '.claude/settings.json'
    if settings.exists():
        previous = None
        if (path / LOCK).exists():
            from development import read_config
            recorded = path / '.repo-standard.json'
            previous_config = read_config(recorded) if recorded.exists() else config
            previous = render(json.loads((path / LOCK).read_text()), previous_config)['.claude/settings.json']
        output['.claude/settings.json'] = merge_settings(
            settings.read_text(), output['.claude/settings.json'], previous)
    if not (path / 'docs/agents/repository.md').exists():
        output['docs/agents/repository.md'] = data['files']['policy/repository.md']
    changed = {}
    for name, value in output.items():
        target = target_path(path, name)
        old = target.read_text() if target.exists() else ''
        if name == '.repo-standard.json' and old and json.loads(old) == config:
            continue
        if old != value or name in EXECUTABLES and not os.access(path / name, os.X_OK):
            changed[name] = value
    return changed


def update(path, source, revision, config, apply=False, *, strict=False):
    path = Path(path).resolve()
    from t3_actions import audit, definitions
    data = snapshot(source, revision)
    print('T3 action inventory (repository file is not effective saved state):')
    for row in audit(target_path(path, 't3.json'), definitions(data['files'])):
        print(json.dumps(row, sort_keys=True))
    if (path / LOCK).exists():
        previous = validate(path, repair_missing_runtime=not strict)
    else:
        previous = None
    changes = plan(path, data, config)
    if previous:
        from development import read_config
        old_output = render(previous, read_config(path / '.repo-standard.json'))
        # Keep local integrations when there is no canonical change to integrate.
        for name in list(changes):
            if ((path / name).exists() and name not in ('.claude/settings.json', '.repo-standard.json')
                    and old_output.get(name) == changes[name]):
                del changes[name]
    status = 'update available' if changes else 'up to date'
    print(f'{status}: canonical revision {data["revision"]}')
    for name, value in changes.items():
        print(f'Planned change: {name}')
        if name == LOCK:
            print('Embedded canonical source and Git object proofs would be refreshed.')
        else:
            old = (path / name).read_text() if (path / name).exists() else ''
            print(''.join(difflib.unified_diff(old.splitlines(True), value.splitlines(True),
                                             fromfile=name, tofile=name)), end='')
    if not apply:
        return changes
    if changes and git(path, 'status', '--porcelain', '--untracked-files=all').strip():
        raise ValueError('Apply requires a clean task checkout; preserve and commit local work first')
    if not previous:
        conflicts = [name for name, value in changes.items()
                     if (path / name).exists() and (path / name).read_text() != value
                     and name not in ('.repo-standard.json', '.claude/settings.json', 't3.json')]
        if conflicts:
            raise ValueError('Adoption conflicts require manual integration before apply: ' + ', '.join(conflicts))
    if previous:
        conflicts = [name for name in changes
                     if name not in ('.claude/settings.json', '.repo-standard.json', 't3.json') and (path / name).exists()
                     and (path / name).read_text() != changes[name]
                     and (name not in old_output or (path / name).read_text() != old_output[name])]
        if conflicts:
            raise ValueError('Local changes conflict with update; integrate manually: ' + ', '.join(conflicts))
    for name, value in changes.items():
        target = target_path(path, name)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(value)
        if name in EXECUTABLES:
            target.chmod(0o755)
    return changes
