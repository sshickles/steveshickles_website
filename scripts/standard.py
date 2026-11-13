#!/usr/bin/env python3
"""Offline, revision-bound rendering and integrity validation.

Git object hashes authenticate the embedded source. This module ships to every
repository; adoption, update and audit tooling stays in sshickles/repo-standard.
"""
import ast
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

CANONICAL = 'sshickles/repo-standard'
LOCK = '.repo-standard-source.json'
# Canonical sources. Files under policy/ are rendered, not copied.
FILES = ['policy/policy.md', 'policy/t3-actions.json', 'CLAUDE.md', 'greptile.json', '.coderabbit.yaml',
         '.claude/settings.json', '.codex/config.toml', '.codex/rules/repo-standard.rules',
         '.gemini/settings.json', '.gemini/policies/repo-standard.toml',
         '.githooks/pre-commit', '.githooks/pre-push', '.github/workflows/ci.yml',
         'scripts/lint-shell', 'scripts/setup', 'scripts/check', 'scripts/test', 'scripts/review',
         'scripts/commands.py', 'scripts/development.py', 'scripts/service_setup.py', 'scripts/pre_commit.py',
         'scripts/pre_push.py', 'scripts/changed_tests.py', 'scripts/standard.py', 'scripts/t3_actions.py', 'scripts/install-hooks.mjs']
EXECUTABLES = ['scripts/lint-shell', 'scripts/setup', 'scripts/check', 'scripts/test', 'scripts/review',
               '.githooks/pre-commit', '.githooks/pre-push']
# Written for the default branch name main; rendered for the configured branch.
BRANCH_RULES = {'.claude/settings.json': False, '.codex/rules/repo-standard.rules': False,
                '.gemini/policies/repo-standard.toml': True}
CI_WORKFLOW = '.github/workflows/ci.yml'
REVIEW_SCOPE_MARKER = '    # repo-standard: managed-path-filters\n'
OPERATOR_SECTION = 'policy/operator.md'

# Paths that carry agent instructions. Anything here that is not generated or
# declared in the facts fails validation.
INSTRUCTION_NAMES = {'AGENTS.md', 'AGENTS.override.md', 'CLAUDE.md', 'GEMINI.md', 'SKILL.md',
                     'gemini-extension.json', 'CONTEXT.md'}
# Agents load these by name wherever they sit, so no fact can exempt them.
RESERVED_NAMES = {'AGENTS.md', 'AGENTS.override.md', 'CLAUDE.md', 'GEMINI.md'}
# The glossary file above and the decision-record folder here are retired conventions that agents
# were told to read and extend. They are caught on the PR that adds one, not later by the audit.
INSTRUCTION_ROOTS = ('.github/instructions/', 'docs/agents/', 'docs/adr/')
# Agents load rules from these folders in any directory, not only the root.
AGENT_FOLDERS = {'.claude', '.codex', '.gemini', '.cursor', '.agents'}
INSTRUCTION_FILES = {'.github/copilot-instructions.md'}
PLUGIN_DIRECTORIES = {'.claude-plugin', '.codex-plugin', '.cursor-plugin'}


def agent_file(name):
    """Agent-facing outputs are replaced exactly on update, never merged."""
    return name == 'AGENTS.md' or name.startswith(('.claude/', '.codex/', '.gemini/'))


def canonical_managed_files(output):
    """Vendored outputs excluded from destination reviews. Every recorded revision renders this same list."""
    return sorted(name for name in output
                  if name != 't3.json' and not name.startswith('.github/workflows/'))


def exact_files(output):
    """Outputs validated byte for byte: the vendored files and, where shipped, the CI workflow."""
    return canonical_managed_files(output) + ([CI_WORKFLOW] if CI_WORKFLOW in output else [])


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


def required_checks(config):
    """Required status contexts: the repository's CI checks plus Greptile."""
    if not config['integrations']['greptile']:
        raise ValueError('Greptile is required; missing integration blocks rollout')
    contexts = {c['context']: c for c in config['ciChecks']}
    if len(contexts) != len(config['ciChecks']):
        raise ValueError('Duplicate ciChecks contexts')
    greptile = {'context': 'Greptile Review', 'integration_id': 867647}
    if 'Greptile Review' in contexts and contexts['Greptile Review'] != greptile:
        raise ValueError('Greptile Review requires integration 867647')
    contexts['Greptile Review'] = greptile
    return list(contexts.values())


def default_branch(text, branch, *, expression=False):
    if not re.fullmatch(r'[A-Za-z0-9._/-]+', branch):
        raise ValueError('git.baseBranch has characters the agent deny rules cannot express')
    value = re.escape(branch) if expression else branch
    return re.sub(r'\bmain\b', lambda _: value, text)


def code(value):
    return '`' + (value if isinstance(value, str) else ' '.join(value)) + '`'


def facts_section(config):
    """Render repository data. Every line comes from .repo-standard.json."""
    facts, dev = config['facts'], config['development']
    lines = ['## Repository facts', '',
             'Rendered from `.repo-standard.json`. These are facts about this repository, not rules.', '',
             f'- Repository: `{config["repository"]}`. {facts["summary"]}',
             f'- Default branch: `{config["git"]["baseBranch"]}` on remote `{config["git"]["remote"]}`.',
             '- Required checks: ' + ', '.join(code(c['context']) for c in required_checks(config)) + '.',
             '- Validation in `./scripts/check`: ' + ', '.join(code(c) for c in config['validation']) + '.',
             '- Test suite: ' + code(config['testCommand']) + '.']
    if 'vercel' in dev:
        lines.append('- Setup pulls the Vercel Development environment into `.env.local`.')
    if 'convex' in dev:
        lines.append(f'- Shared Convex development deployment: `{dev["convex"]["deployment"]}`.')
        for name, target in dev['convex'].get('additionalDeployments', {}).items():
            lines.append(f'- Additional Convex development deployment `{name}`: `{target["deployment"]}`.')
    if facts['backendFolders']:
        lines.append('- Backend folders: ' + ', '.join(code(name + '/') for name in facts['backendFolders']) + '.')
    if facts['plugins']:
        lines.append('- Shipped product plugins: ' + ', '.join(code(name + '/') for name in facts['plugins']) + '.')
    if facts.get('shippedInstructionFiles'):
        lines.append('- Product content, not instructions for work in this repository: '
                     + ', '.join(code(name) for name in facts['shippedInstructionFiles']) + '.')
    sections = (
        ('Commands', [f'- {code(c["command"])}: {c["purpose"]}' for c in facts['commands']]),
        ('Deployments', [f'- {d["name"]}: {d["service"]}, {d["environment"]}, {d["trigger"]}'
                         + (f', {d["url"]}' if 'url' in d else '') for d in facts['deployments']]),
        ('Services', [f'- {s["name"]}: {s["purpose"]}' for s in facts['services']]),
        ('Enforced product rules', [f'- {code(r["doc"])}, enforced by {code(r["check"])}.'
                                    for r in facts['productRules']]),
    )
    for title, rows in sections:
        if rows:
            lines += ['', '### ' + title, '', *rows]
    if 'convex' in facts:
        lines += ['', '### Convex', '', f'Before backend changes, read `{facts["convex"]["guidelines"]}`.']
    return '\n'.join(lines) + '\n'


def instructions(data, config, policy):
    """The one self-contained instruction file: shared policy, then repository facts."""
    header = (f'<!-- Generated from {CANONICAL}@{data["revision"]}. Do not edit. '
              'Rules come from the canonical policy; facts come from .repo-standard.json. -->\n')
    return header + policy.rstrip('\n') + '\n\n' + facts_section(config)


def manifest(files):
    """The file list the embedded revision itself declares, so a lock cannot quietly drop a managed file."""
    source = files.get('scripts/standard.py')
    if source is not None:
        for node in ast.parse(source).body:
            if isinstance(node, ast.Assign) and any(getattr(t, 'id', None) == 'FILES' for t in node.targets):
                return ast.literal_eval(node.value)
    raise ValueError('Canonical snapshot omits its own manifest: scripts/standard.py')


def render(data, config):
    files = verify_snapshot(data)
    missing = [name for name in manifest(files) if name not in files]
    if missing:
        raise ValueError('Canonical snapshot omits managed files: ' + ', '.join(missing))
    branch = config['git']['baseBranch']
    output = {name: value for name, value in files.items() if not name.startswith('policy/')}
    output['AGENTS.md'] = instructions(data, config, files['policy/policy.md'])
    for name, expression in BRANCH_RULES.items():
        output[name] = default_branch(output[name], branch, expression=expression)
    output[LOCK] = json_text(data)
    from t3_actions import definitions, merge
    output['t3.json'] = json_text(merge({}, definitions(files)))
    if config.get('existingCI'):
        output.pop(CI_WORKFLOW, None)
    else:
        # Written for GitHub-hosted runners; a repository may name another runner label.
        output[CI_WORKFLOW] = output[CI_WORKFLOW].replace(
            'runs-on: ubuntu-latest', 'runs-on: ' + config.get('ciRunner', 'ubuntu-latest'))
    greptile = json.loads(files['greptile.json'])
    greptile['autoApprove']['filters']['includeRepositories'] = [config['repository']]
    if config['repository'].lower() != CANONICAL:
        # Generated files are reviewed once, in the canonical repository.
        managed = canonical_managed_files(output)
        filters = ''.join('    - ' + json.dumps('!' + name) + '\n' for name in managed)
        output['.coderabbit.yaml'] = output['.coderabbit.yaml'].replace(
            REVIEW_SCOPE_MARKER, REVIEW_SCOPE_MARKER + filters)
        greptile['ignorePatterns'] = (greptile.get('ignorePatterns', '').rstrip('\n') + '\n'
                                      + '\n'.join('/' + name for name in managed))
    output['greptile.json'] = json_text(greptile)
    return output


def expected_outputs(path, data, config):
    """Rendered files for this checkout. The canonical repository adds its operator rules."""
    output = render(data, config)
    if config['repository'] == CANONICAL:
        output['AGENTS.md'] += '\n' + target_path(Path(path), OPERATOR_SECTION).read_text()
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
    block = job_block(target_path(path, ci['workflow']).read_text(), ci['job'])
    if block is None:
        raise ValueError('existingCI job must be a block-style job in the selected workflow')
    name = re.search(r'^    name: *([^\n]+)$', block, re.M)
    context = workflow_scalar(name[1]) if name else ci['job']
    if context != ci['context']:
        raise ValueError('existingCI job name differs from its required context')
    if not runs_check(block):
        raise ValueError('existingCI job requires a standalone run: ./scripts/check step')


def job_block(text, job):
    """The body of one block-style workflow job, or None."""
    jobs = re.search(r'^jobs:\s*\n((?:[ \t]+[^\n]*\n|\n)*)', text + '\n', re.M)
    block = re.search(r'^  ' + re.escape(job) + r':\s*\n((?:    [^\n]*\n|\n)*)', jobs[1], re.M) if jobs else None
    return block[1] if block else None


def runs_check(block):
    """True when the job has an unconditional ./scripts/check step whose failure fails the job."""
    if re.search(r'^    continue-on-error: *(?!false\b)\S', block, re.M):
        return False
    for step in re.split(r'^      - ', block, flags=re.M)[1:]:
        run = re.search(r'^(?:        )?run: *([^\n]+)$', step, re.M)
        if (run and workflow_scalar(run[1]) in ('./scripts/check', './scripts/check --all')
                and not re.search(r'^        continue-on-error: *(?!false\b)\S', step, re.M)
                and not re.search(r'^        if:', step, re.M)):
            return True
    return False


def instruction_path(name):
    parts = Path(name).parts
    return (parts[-1] in INSTRUCTION_NAMES or name in INSTRUCTION_FILES or name.startswith(INSTRUCTION_ROOTS)
            or bool((PLUGIN_DIRECTORIES | AGENT_FOLDERS) & set(parts[:-1])))


def tracked_files(path):
    """Committed and staged paths. Ignored local tool state never reaches a push."""
    names = subprocess.run(['git', 'ls-files', '-z', '--cached'], cwd=path, capture_output=True, text=True)
    if names.returncode:
        raise ValueError('Cannot list tracked files')
    return [name for name in names.stdout.split('\0') if name and (Path(path) / name).is_file()]


def unmanaged_instructions(path, config, managed):
    """Instruction-bearing files that are neither generated nor declared as facts."""
    facts = config['facts']
    declared = {rule['doc'] for rule in facts['productRules']}
    if 'convex' in facts:
        declared.add(facts['convex']['guidelines'])
    plugins = tuple(name + '/' for name in facts['plugins'])
    # A file agents load by name passes only at an exact path the facts list, never through a folder.
    shipped = set(facts.get('shippedInstructionFiles', []))
    def exempt(name):
        if Path(name).name in RESERVED_NAMES:
            return name in shipped
        return name in declared or name.startswith(plugins)
    return [name for name in tracked_files(path)
            if instruction_path(name) and name not in managed and not exempt(name)]


def validate_facts(path, config):
    """Declared facts must describe files that exist in this checkout."""
    facts = config['facts']
    for name in facts['plugins'] + facts['backendFolders']:
        if not (path / name).is_dir():
            raise ValueError(f'Declared fact is not a directory in this checkout: {name}')
    for rule in facts['productRules']:
        if not (path / rule['doc']).is_file():
            raise ValueError(f'Product rule document is missing: {rule["doc"]}')
    for name in facts.get('shippedInstructionFiles', []):
        if not (path / name).is_file() or (path / name).is_symlink():
            raise ValueError(f'Shipped instruction file is not a regular file in this checkout: {name}')
    if 'convex' not in facts:
        return
    guidelines = path / facts['convex']['guidelines']
    if not guidelines.is_file():
        raise ValueError(f'Convex guidelines file is missing: {facts["convex"]["guidelines"]}')
    # Convex may refresh its guidelines file. It must not write agent files or skills.
    disabled = False
    if (path / 'convex.json').is_file():
        settings = json.loads((path / 'convex.json').read_text()).get('aiFiles')
        disabled = isinstance(settings, dict) and settings.get('enabled') is False
    state = guidelines.parent / 'ai-files.state.json'
    if state.is_file() and not disabled:
        recorded = json.loads(state.read_text())
        if any(recorded.get(key) for key in ('agentsMdSectionHash', 'claudeMdHash', 'agentSkillsSha')):
            raise ValueError('Convex agent-file installer is active: run `npx convex ai-files disable`, or clear the '
                             'AGENTS.md, CLAUDE.md and skills entries in ' + str(state.relative_to(path)))


def validate(path, *, repair=False, hooks=True, tolerate=()):
    """Check this checkout against its recorded canonical revision.

    repair tolerates what an update rewrites: missing generated files and drifted agent files.
    tolerate names files an update removes, whose local content no longer matters.
    """
    from development import read_config, validate_services
    path = Path(path).resolve()
    config = read_config(path / '.repo-standard.json')
    validate_services(path, config)
    validate_existing_ci(path, config)
    if config['repository'] == CANONICAL:
        if (config['integrations']['deploymentCheck'] is not None
                or {'context': 'Greptile Review', 'integration_id': 867647} not in config['ciChecks']):
            raise ValueError('Canonical configuration drift: no deployment target; ciChecks must include Greptile Review integration 867647')
    required_checks(config)
    if not config.get('existingCI') and 'checks' not in [check['context'] for check in config['ciChecks']]:
        # The shipped workflow is byte-checked below; its checks job reports this context.
        raise ValueError('ciChecks must list the checks context the shipped workflow reports, '
                         'or existingCI must name the workflow that reports another')
    data = json.loads((path / LOCK).read_text())
    expected = expected_outputs(path, data, config)
    for name in expected:
        target_path(path, name)
    from t3_actions import definitions, validate as validate_actions
    canonical = definitions(verify_snapshot(data))
    t3 = path / 't3.json'
    if not (repair and not t3.exists()):
        if not t3.is_file():
            raise ValueError('Canonical-managed file missing: t3.json')
        document = json.loads(t3.read_text())
        try:
            validate_actions(document, canonical)
        except ValueError:
            # Conflicts carry the same exact manual diff during updates as adoption.
            from t3_actions import merge
            merge(document, canonical)
            raise
    for name in exact_files(expected):
        if name == LOCK or name in tolerate:
            continue  # Git proofs cover the lock; an update deletes the tolerated files.
        target = path / name
        if not target.exists():
            if repair:
                continue
            raise ValueError(f'Canonical-managed file missing: {name}')
        if not target.is_file():
            raise ValueError(f'Canonical-managed path must be a regular file: {name}')
        if name == 'greptile.json':
            if json.loads(target.read_text()) != json.loads(expected[name]):
                raise ValueError('Configuration drift: greptile.json')
        elif target.read_bytes() != expected[name].encode() and not (repair and agent_file(name)):
            raise ValueError(f'Canonical-managed file drift: {name}'
                             + ('; run python3 scripts/standard.py render' if agent_file(name) else ''))
    for name in EXECUTABLES:
        if (path / name).is_file() and not os.access(path / name, os.X_OK):
            raise ValueError(f'Required executable missing: {name}')
    if config['repository'] == CANONICAL and not repair:
        # 3. Here the sources and the lock travel together: a changed or deleted source needs a new stamp.
        for name, content in data['files'].items():
            if not (path / name).is_file() or (path / name).read_bytes() != content.encode():
                raise ValueError('Canonical source differs from the recorded revision; commit it, then stamp: ' + name)
    if not repair:
        stray = unmanaged_instructions(path, config, set(expected))
        if stray:
            raise ValueError('Unmanaged instruction files; move rules to sshickles/repo-standard, '
                             'declare product plugins in the facts, or delete: ' + ', '.join(stray))
        validate_facts(path, config)
    from pre_push import repository_checks
    repository_checks(path)
    repository_checks(path, '.githooks/doctor.d')
    if hooks:
        installed = subprocess.run(['git', 'config', '--local', '--get', 'core.hooksPath'],
                                   cwd=path, capture_output=True, text=True)
        if installed.stdout.strip() != '.githooks':
            raise ValueError('Hook installation missing: run ./scripts/setup')
    print(f'Instructions and required structure valid at {data["revision"]}')
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


def rerender(path):
    """Rewrite generated files from the recorded revision after a facts change."""
    from development import read_config
    path = Path(path).resolve()
    config = read_config(path / '.repo-standard.json')
    data = json.loads((path / LOCK).read_text())
    expected = expected_outputs(path, data, config)
    written = []
    for name in exact_files(expected):
        target = target_path(path, name)
        runnable = name in EXECUTABLES
        if name != LOCK and (not target.is_file() or target.read_bytes() != expected[name].encode()
                             or runnable and not os.access(target, os.X_OK)):
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(expected[name])
            if runnable:
                target.chmod(0o755)
            written.append(name)
    print('Rendered: ' + (', '.join(written) or 'already current'))
    return written


def main(argv):
    usage = 'usage: standard.py {validate|render} [path]'
    if len(argv) not in (1, 2) or argv[0] not in ('validate', 'render'):
        print(usage, file=sys.stderr)
        return 2
    path = argv[1] if len(argv) == 2 else Path(__file__).resolve().parent.parent
    try:
        (validate if argv[0] == 'validate' else rerender)(path)
    except (OSError, ValueError, KeyError, TypeError, subprocess.CalledProcessError) as error:
        print(f'Error: {error}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
