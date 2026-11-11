"""Pull Development values and attach to an existing shared Convex deployment."""
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import tempfile

# Keep whole dotenv assignments, including quoted multiline values, intact.
ASSIGNMENT = re.compile(
    r'^[ \t]*(?:export[ \t]+)?([A-Za-z_][A-Za-z0-9_]*)[ \t]*=[ \t]*'
    r'(?:"(?:\\[\s\S]|[^"\\])*"|\'[^\']*\'|`[^`]*`|[^\r\n]*)[^\r\n]*(?:\r?\n|$)', re.M)
OVERRIDES = ('CONVEX_DEPLOY_KEY', 'CONVEX_DEPLOYMENT_TOKEN',
             'CONVEX_SELF_HOSTED_URL', 'CONVEX_SELF_HOSTED_ADMIN_KEY')


def entries(text):
    return {match[1]: match[0] for match in ASSIGNMENT.finditer(text)}


def value(assignment):
    raw = assignment.split('=', 1)[1].strip()
    if raw.startswith(('"', "'", '`')):
        return raw[1:].split(raw[0], 1)[0]
    return raw.split('#', 1)[0].strip()


def overlay(text, replacements):
    """Replace only named assignments; retain unrelated text and local-only keys."""
    remaining = dict(replacements)
    def replace(match):
        if match[1] not in replacements:
            return match[0]
        # Drop duplicate assignments so stale selectors cannot win.
        return remaining.pop(match[1], '')
    result = ASSIGNMENT.sub(replace, text)
    if remaining and result and not result.endswith('\n'):
        result += '\n'
    return result + ''.join(remaining.values())


def invoke(root, command, instruction):
    try:
        result = subprocess.run(['mise', 'exec', '--', *command], cwd=root,
                                stdin=subprocess.DEVNULL, capture_output=True, text=True,
                                timeout=120, env={**os.environ, 'MISE_AUTO_INSTALL': '0', 'CI': '1'})
    except (OSError, subprocess.TimeoutExpired):
        raise RuntimeError(instruction) from None
    if result.returncode:
        raise RuntimeError(instruction)
    return result.stdout


def deployment_url(dev):
    convex = dev['convex']
    return convex.get('url', 'https://' + convex['deployment'][4:] + '.convex.cloud')


def attachment(dev):
    convex = dev.get('convex')
    if not convex:
        return {}
    values = {'CONVEX_DEPLOYMENT': convex['deployment']}
    if 'urlVariable' in convex:
        values[convex['urlVariable']] = deployment_url(dev)
    return values


def validate_attachment(root, dev, text):
    current = {key: value(raw) for key, raw in entries(text).items()}
    for key in dev['vercel'].get('requiredKeys', []):
        if not current.get(key, '').strip():
            raise ValueError('Missing or empty required Vercel Development key: ' + key)
    expected = attachment(dev)
    if not expected:
        return
    defaults = root / '.env'
    default_values = ({key: value(raw) for key, raw in entries(defaults.read_text()).items()}
                      if defaults.is_file() else {})
    for target in dev['convex'].get('additionalDeployments', {}).values():
        key = target['deployKeyVariable']
        candidates = [current.get(key, '')]
        candidates.extend(source[key] for source in (default_values, os.environ) if key in source)
        for candidate in candidates:
            prefix, separator, credential = candidate.partition('|')
            if prefix != target['deployment'] or not separator or not credential.strip():
                raise ValueError('Convex key ' + key + ' must target its configured dev deployment')
    for key in OVERRIDES:
        if current.get(key) or default_values.get(key) or os.environ.get(key):
            raise ValueError('Remove conflicting Convex credentials or selectors from the shell and environment files')
    for key, wanted in expected.items():
        if current.get(key) != wanted or os.environ.get(key, wanted) != wanted:
            raise ValueError('Shared Convex attachment mismatch; run ./scripts/setup with conflicting shell selectors unset')


def verify(root, dev, text):
    validate_attachment(root, dev, text)
    if not attachment(dev):
        return
    cli = root / 'node_modules/.bin/convex'
    if not cli.is_file():
        raise ValueError('Install the locked Convex dependency before service setup')
    output = invoke(root, [str(cli), 'function-spec', '--env-file', '.env.local'],
                    'Convex read-only verification failed; verify existing Convex login and shared deployment access')
    try:
        actual = json.loads(output)['url']
    except (ValueError, KeyError, TypeError):
        raise ValueError('Convex read-only verification returned no deployment identity') from None
    if actual != deployment_url(dev):
        raise ValueError('Convex read-only verification selected a different deployment')


def protect_environment(root, *, repair):
    """Keep the final artifact and interrupted staging out of commits and review."""
    tracked = subprocess.run(['git', 'ls-files', '--error-unmatch', '--', '.env.local'],
                             cwd=root, capture_output=True)
    if tracked.returncode == 0:
        raise ValueError('.env.local is tracked; remove it from tracking before pulling service values')
    if tracked.returncode != 1:
        raise ValueError('Cannot check whether .env.local is tracked')
    result = subprocess.run(['git', 'rev-parse', '--git-path', 'info/exclude'],
                            cwd=root, capture_output=True, text=True)
    if result.returncode:
        raise ValueError('Cannot determine the checkout Git exclude path')
    name = result.stdout.strip()
    path = root / name
    existing = path.read_text() if path.exists() else ''
    missing = [pattern for pattern in ('/.env.local', '/.repo-standard-env-*/')
               if pattern not in existing.splitlines()]
    if repair and missing:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open('a') as stream:
            stream.write('\n' + '\n'.join(missing) + '\n')
    ignored = subprocess.run(['git', 'check-ignore', '--quiet', '--', '.env.local'], cwd=root)
    if ignored.returncode:
        raise ValueError('.env.local must be ignored by Git; run setup or remove conflicting ignore overrides')


def prepare(root, dev, *, doctor=False):
    root = Path(root)
    path = root / '.env.local'
    if path.is_symlink():
        raise ValueError('.env.local must be a checkout-owned regular file, not a symlink')
    if path.exists():
        if not path.is_file():
            raise ValueError('.env.local must be a checkout-owned regular file')
        if doctor:
            if stat.S_IMODE(path.stat().st_mode) != 0o600:
                raise ValueError('.env.local must have mode 0600; run ./scripts/setup')
        else:
            path.chmod(0o600)
    protect_environment(root, repair=not doctor)
    link = root / '.vercel/project.json'
    try:
        project = json.loads(link.read_text())
        linked = all(isinstance(project.get(key), str) and project[key] for key in ('projectId', 'orgId'))
    except (OSError, ValueError, AttributeError):
        linked = False
    if not linked:
        raise ValueError('Vercel project link missing or invalid; link the existing project with vercel link before setup')
    for key in ('projectId', 'orgId'):
        if key in dev['vercel'] and project[key] != dev['vercel'][key]:
            raise ValueError('Vercel project link mismatch for ' + key + '; link the configured existing project separately')
    for variable, key in (('VERCEL_PROJECT_ID', 'projectId'), ('VERCEL_ORG_ID', 'orgId')):
        if os.environ.get(variable, project[key]) != project[key]:
            raise ValueError('Vercel shell project selectors conflict with the checkout link; unset them before setup')
    invoke(root, ['vercel', 'whoami'], 'Vercel login unavailable; run vercel login separately before setup')
    old = path.read_text() if path.exists() else ''
    if doctor:
        if not path.is_file():
            raise ValueError('Missing .env.local; run ./scripts/setup')
    else:
        # Stage on the checkout filesystem so replacement stays atomic even
        # when the worktree's Git directory lives on a different mount.
        with tempfile.TemporaryDirectory(prefix='.repo-standard-env-', dir=root) as temporary:
            pulled = Path(temporary) / '.env.local'
            ignored = subprocess.run(['git', 'check-ignore', '--quiet', '--', str(pulled)], cwd=root)
            if ignored.returncode:
                raise ValueError('Private setup staging must be ignored by Git; remove conflicting ignore overrides')
            invoke(root, ['vercel', 'env', 'pull', str(pulled), '--environment', 'development', '--yes'],
                   'Vercel Development pull failed; verify existing login and project link')
            if not pulled.is_file():
                raise ValueError('Vercel Development pull did not produce an environment file')
            source = pulled.read_text()
            if '[SENSITIVE]' in source:
                raise ValueError('Vercel Development contains unavailable sensitive placeholders; correct its configuration')
            updates = {key: raw if raw.endswith('\n') else raw + '\n'
                       for key, raw in entries(source).items()}
            updates.update({key: key + '=' + json.dumps(wanted) + '\n' for key, wanted in attachment(dev).items()})
            text = overlay(old, updates)
            validate_attachment(root, dev, text)
            if text != old or not path.exists():
                staged = Path(temporary) / 'attached.env'
                staged.write_text(text)
                staged.chmod(0o600)
                staged.replace(path)
    verify(root, dev, path.read_text())
