"""Offline, revision-bound rendering. Git object hashes authenticate embedded source."""
import base64
import difflib
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
         'scripts/commands.py', 'scripts/development.py', 'scripts/service_setup.py', 'scripts/pre_push.py', 'scripts/changed_tests.py',
         'scripts/repository.py', 'scripts/standard.py', 'scripts/halo.py',
         'scripts/worktree.py', 'scripts/wt.sh', 'scripts/install-hooks.mjs']
EXECUTABLES = ['scripts/lint-shell', 'scripts/new-repo', 'apply-ruleset.sh', 'scripts/setup', 'scripts/check', 'scripts/test', 'scripts/review', '.githooks/pre-push', 'scripts/wt.sh']

def runtime_files(output):
    return [name for name in output
            if (name.startswith('scripts/') and name.endswith(('.py', '.mjs'))) or name == 't3.json']


REVIEW_SCOPE_MARKER = '    # repo-standard: managed-path-filters\n'
AGENT_FILES_MARKER = '# repo-standard: canonical-agent-files\n'


def canonical_managed_files(output):
    """Exact vendored outputs; stack-specific integrations remain reviewable."""
    local = {'t3.json'}
    return sorted(name for name in output
                  if name not in local and not name.startswith('.github/workflows/'))


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
    contexts = {c['context']: c for c in config['ciChecks']}
    if len(contexts) != len(config['ciChecks']):
        raise ValueError('Duplicate ciChecks contexts')
    greptile = {'context': 'Greptile Review', 'integration_id': 867647}
    if 'Greptile Review' in contexts and contexts['Greptile Review'] != greptile:
        raise ValueError('Greptile Review requires integration 867647')
    contexts['Greptile Review'] = greptile
    checks['parameters']['required_status_checks'] = list(contexts.values())
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
    if config.get('existingCI'):
        output.pop('.github/workflows/ci.yml', None)
    if REVIEW_SCOPE_MARKER in files['.coderabbit.yaml'] and config['repository'].lower() != CANONICAL:
        managed = canonical_managed_files(output)
        # A recorded revision must keep the filters its renderer shipped, so
        # existing installs validate before update replaces both review configs.
        if AGENT_FILES_MARKER not in files['.coderabbit.yaml']:
            managed = [name for name in managed if name not in ('AGENTS.md', '.claude/settings.json')]
        filters = ''.join('    - ' + json.dumps('!' + name) + '\n' for name in managed)
        output['.coderabbit.yaml'] = output['.coderabbit.yaml'].replace(
            REVIEW_SCOPE_MARKER, REVIEW_SCOPE_MARKER + filters)
        greptile['ignorePatterns'] = greptile.get('ignorePatterns', '').rstrip('\n') + '\n' + '\n'.join('/' + name for name in managed)
        output['greptile.json'] = json_text(greptile)
    return output


def workflow_scalar(value):
    """Read a single-line workflow string, preserving quoted comment characters."""
    value = value.strip()
    if value.startswith('"'):
        result, end = json.JSONDecoder().raw_decode(value)
    elif value.startswith("'"):
        quoted = re.match(r"'((?:[^']|'')*)'", value)
        if not quoted:
            raise ValueError('Unterminated workflow string')
        result, end = quoted[1].replace("''", "'"), quoted.end()
    else:
        return re.split(r'\s+#', value, maxsplit=1)[0].rstrip()
    if not re.fullmatch(r'(?:\s+#.*)?\s*', value[end:]):
        raise ValueError('Expected a single workflow string with an optional comment')
    return result


def validate_existing_ci(path, config):
    ci = config.get('existingCI')
    if not ci:
        return
    # Accept a conventional block-style job. Unsupported YAML must be reconciled
    # explicitly instead of mistaking a comment or another job for the check.
    # read_text uses universal newlines, including for workflows stored with CRLF.
    text = target_path(path, ci['workflow']).read_text()
    jobs = re.search(r'^jobs:\s*\n((?:[ \t]+[^\n]*\n|\n)*)', text + '\n', re.M)
    block = re.search(r'^  ' + re.escape(ci['job']) + r':\s*\n((?:    [^\n]*\n|\n)*)', jobs[1], re.M) if jobs else None
    if not block:
        raise ValueError('existingCI job must be a block-style job in the selected workflow')
    name = re.search(r'^    name: *([^\n]+)$', block[1], re.M)
    context = workflow_scalar(name[1]) if name else ci['job']
    if context != ci['context']:
        raise ValueError('existingCI job name differs from its required context')
    runs = re.findall(r'^      - run: *([^\n]+)$', block[1], re.M)
    if not any(workflow_scalar(value) == './scripts/check' for value in runs):
        raise ValueError('existingCI job requires a standalone run: ./scripts/check step')


def validate(path, *, repair_missing_runtime=False, repair_agent_settings=False):
    from development import read_config, validate_services
    path = Path(path).resolve()
    config = read_config(path / '.repo-standard.json')
    validate_services(path, config)
    validate_existing_ci(path, config)
    if config['repository'] == CANONICAL:
        if (config['integrations']['deploymentCheck'] is not None
                or {'context': 'Greptile Review', 'integration_id': 867647} not in config['ciChecks']):
            raise ValueError('Canonical configuration drift: no deployment target; ciChecks must include Greptile Review integration 867647')
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
        document = json.loads(t3.read_text())
        try:
            validate_actions(document, canonical)
        except ValueError:
            # Conflicts carry the same exact manual diff during updates as adoption.
            from t3_actions import merge
            merge(document, canonical)
            raise
    if (path / 'docs/agents/policy.md').read_text() != expected['docs/agents/policy.md']:
        raise ValueError('Generated policy drift from recorded canonical revision')
    # Local configuration is checked separately from shared policy content.
    for name in ('ruleset.json', 'greptile.json'):
        if json.loads((path / name).read_text()) != json.loads(expected[name]):
            raise ValueError(f'Configuration drift: {name}')
    for name in ('AGENTS.md', '.claude/settings.json'):
        if not repair_agent_settings and (not (path / name).is_file()
                or (path / name).read_bytes() != expected[name].encode()):
            raise ValueError('Canonical-managed file drift: ' + name)
    if (path / '.coderabbit.yaml').read_text() != expected['.coderabbit.yaml']:
        raise ValueError('Configuration drift: .coderabbit.yaml')
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
    # Review exclusions are safe only for files checked against the same source.
    # Older locks predate this contract and keep their existing validation rules.
    if REVIEW_SCOPE_MARKER in data['files']['.coderabbit.yaml']:
        for name in canonical_managed_files(expected):
            if repair_agent_settings and name in ('AGENTS.md', '.claude/settings.json'):
                continue
            if name in (LOCK, 'ruleset.json', 'greptile.json'):
                continue  # Git proofs and structured JSON checks cover these below.
            target = path / name
            if not target.exists():
                if repair_missing_runtime:
                    continue
                raise ValueError(f'Canonical-managed file missing: {name}')
            if not target.is_file():
                raise ValueError(f'Canonical-managed path must be a regular file: {name}')
            if target.read_text() != expected[name]:
                raise ValueError(f'Canonical-managed file drift: {name}')
    from pre_push import repository_checks
    repository_checks(path)
    repository_checks(path, '.githooks/doctor.d')
    hooks = subprocess.run(['git', 'config', '--local', '--get', 'core.hooksPath'], cwd=path, capture_output=True, text=True)
    if hooks.stdout.strip() != '.githooks':
        raise ValueError('Hook installation missing: run ./scripts/setup')
    print(f'Policy and required structure valid at {data["revision"]}')
    return data


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
    from development import validate_services
    validate_services(path, config)
    validate_existing_ci(path, config)
    output = render(data, config)
    if config['profile'] == 'custom' and not target_path(path, 'mise.toml').exists():
        output['mise.toml'] = '[tools]\n' + ''.join(
            json.dumps(k) + ' = ' + json.dumps(v) + '\n'
            for k, v in config['development'].get('tools', {}).items())
    output['.repo-standard.json'] = json_text(config)
    from t3_actions import definitions, merge
    canonical = definitions(data['files'])
    t3 = target_path(path, 't3.json')
    if canonical and t3.exists():
        output['t3.json'] = json_text(merge(json.loads(t3.read_text()), canonical))
    if not (path / 'docs/agents/repository.md').exists():
        output['docs/agents/repository.md'] = data['files']['policy/repository.md']
    changed = {}
    for name, value in output.items():
        target = target_path(path, name)
        old = target.read_bytes() if target.exists() else b''
        if name == '.repo-standard.json' and old and json.loads(old) == config:
            continue
        if old != value.encode() or name in EXECUTABLES and not os.access(path / name, os.X_OK):
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
        previous = validate(path, repair_missing_runtime=not strict, repair_agent_settings=not strict)
    else:
        previous = None
    changes = plan(path, data, config)
    if previous:
        from development import read_config
        old_output = render(previous, read_config(path / '.repo-standard.json'))
        managed = (set(canonical_managed_files(render(data, config)))
                   if REVIEW_SCOPE_MARKER in data['files']['.coderabbit.yaml'] else set())
        # Keep local integrations only where the new revision permits overrides.
        # Newly integrity-locked files must reach the conflict check before writes.
        for name in list(changes):
            if ((path / name).exists() and name not in ('AGENTS.md', '.claude/settings.json', '.repo-standard.json')
                    and name not in managed
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
                     and name not in ('.repo-standard.json', 'AGENTS.md', '.claude/settings.json', 't3.json')]
        if conflicts:
            raise ValueError('Adoption conflicts require manual integration before apply: ' + ', '.join(conflicts))
    if previous:
        conflicts = [name for name in changes
                     if name not in ('AGENTS.md', '.claude/settings.json', '.repo-standard.json', 't3.json') and (path / name).exists()
                     and (path / name).read_text() != changes[name]
                     and (name not in old_output or (path / name).read_text() != old_output[name])]
        if conflicts:
            raise ValueError('Local changes conflict with update; integrate manually: ' + ', '.join(conflicts))
    for name in sorted(changes, key=lambda name: name == LOCK):
        value = changes[name]
        target = target_path(path, name)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(value)
        if name in EXECUTABLES:
            target.chmod(0o755)
    return changes
