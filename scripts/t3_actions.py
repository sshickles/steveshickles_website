"""Repository action generation and report-only T3 inventory."""
import copy
import json


def definitions(files):
    """Older source locks predate canonical actions and remain valid for upgrades."""
    raw = files.get('policy/t3-actions.json')
    if raw is None:
        return []
    scripts = scripts_from(json.loads(raw))
    commands = ['./scripts/' + name for name in ('setup', 'check', 'test', 'review')]
    if len(scripts) != 4 or [s['command'] for s in scripts] != commands:
        raise ValueError('Canonical T3 definitions must contain setup, check, test, review once')
    if len({s['name'] for s in scripts}) != 4:
        raise ValueError('Duplicate canonical T3 action name')
    for index, script in enumerate(scripts):
        if not script['name'].strip() or script.get('icon') not in ('play', 'test', 'lint', 'configure', 'build', 'debug'):
            raise ValueError('Invalid canonical T3 name or icon')
        if script.get('runOnWorktreeCreate') is not (index == 0):
            raise ValueError('Invalid canonical creation flag')
        if index == 0 and script.get('async') is not False:
            raise ValueError('Canonical setup must wait synchronously')
        if any(script.get(key) is not False for key in ('runOnSettle', 'stopOnSettle')):
            raise ValueError('Canonical actions must not run or stop on settle')
    return scripts


def scripts_from(document):
    if not isinstance(document, dict) or not isinstance(document.get('scripts', []), list):
        raise ValueError('T3 file must contain an object with a scripts array')
    scripts = document.get('scripts', [])
    if any(not isinstance(s, dict) or not isinstance(s.get('name'), str)
           or not isinstance(s.get('command'), str) for s in scripts):
        raise ValueError('T3 scripts require string names and commands')
    return scripts


def matches(script, wanted):
    return script['name'] == wanted['name'] or script['command'] == wanted['command']


def validate(document, canonical):
    scripts = scripts_from(document)
    for wanted in canonical:
        found = [s for s in scripts if matches(s, wanted)]
        if len(found) != 1 or any(found[0].get(k) != v or type(found[0].get(k)) is not type(v)
                                  for k, v in wanted.items()):
            raise ValueError('T3 action drift or duplicate: ' + wanted['name'])
    if canonical and any(s.get('runOnWorktreeCreate') for s in scripts if s['command'] != './scripts/setup'):
        raise ValueError('Competing T3 creation action: fold its behavior into ./scripts/setup')


def merge(document, canonical):
    result = copy.deepcopy(document)
    retained = []
    for script in scripts_from(document):
        found = [s for s in canonical if matches(script, s)]
        if found:
            if script.keys() - found[0].keys():
                raise ValueError('Preserve extra action fields manually before replacing: ' + script['name'])
            if any(script['command'] != wanted['command'] for wanted in found):
                raise ValueError('Preserve repository action manually before replacing: ' + script['name'])
            if script.get('runOnWorktreeCreate') and script['command'] != './scripts/setup':
                raise ValueError('Fold repository creation behavior into ./scripts/setup before updating')
            # Lifecycle additions carry behavior too. Do not silently delete settle hooks.
            if script.get('runOnSettle') or script.get('stopOnSettle'):
                raise ValueError('Preserve settle behavior in a separate action: ' + script['name'])
        else:
            if script.get('runOnWorktreeCreate'):
                raise ValueError('Fold repository creation behavior into ./scripts/setup before updating')
            retained.append(script)
    result.setdefault('$schema', 'https://t3.codes/schema/t3.json')
    result.setdefault('defaultThreadEnvMode', 'worktree')
    result['scripts'] = copy.deepcopy(canonical) + retained
    validate(result, canonical)
    return result


def audit(path, canonical):
    """No live settings access from CI. Never infer saved state from a project file."""
    try:
        document = json.loads(path.read_text())
        scripts = scripts_from(document)
    except FileNotFoundError:
        document, scripts = {}, []
    except (OSError, ValueError, TypeError):
        return [{'scope': 'repository', 'status': 'inaccessible', 'detail': 'Cannot decode/read t3.json'},
                *host_inventory()]
    rows = []
    for wanted in canonical:
        found = [s for s in scripts if matches(s, wanted)]
        try:
            validate({'scripts': found}, [wanted])
            status = 'aligned'
        except ValueError:
            status = 'pending'
        rows.append({'scope': 'repository', 'action': wanted['name'], 'status': status,
                     'command': wanted['command']})
    competing = [s['name'] for s in scripts if s.get('runOnWorktreeCreate') and s['command'] != './scripts/setup']
    rows.append({'scope': 'repository lifecycle', 'status': 'pending' if competing else 'aligned',
                 'competingCreationActions': competing,
                 'settleActions': [s['name'] for s in scripts if s.get('runOnSettle')],
                 'stopOnSettleActions': [s['name'] for s in scripts if s.get('stopOnSettle')]})
    return rows + host_inventory()


def host_inventory():
    return [{'scope': 'host saved actions, overrides and keybindings', 'status': 'unsupported',
             'detail': 'No supported settings-read CLI in T3 0.1.8. Use supported settings UI and project/environment read tools per host; see docs/t3-compatibility.md. Effective host state remains pending.'}]
