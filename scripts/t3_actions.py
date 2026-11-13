"""Repository action generation and report-only T3 inventory."""
import copy
import difflib
import json

# Each action calls its script without arguments, so a saved host action never needs editing when a
# script's behavior changes. ./scripts/check without arguments is the working check.
COMMANDS = ['./scripts/setup', './scripts/check', './scripts/test', './scripts/review']
# Commands an earlier revision shipped for the same action. A recorded lock may still carry one,
# and an update replaces an action that still has one instead of reporting a conflict.
SUPERSEDED = {'./scripts/check': ('./scripts/check --changed',)}
# While the check action carried its earlier command, the command without arguments ran the full
# suite. A repository's own action from then keeps that meaning under its current spelling.
RESPELLED = {'./scripts/check': './scripts/check --all'}


def definitions(files):
    """Older source locks predate canonical actions and remain valid for upgrades."""
    raw = files.get('policy/t3-actions.json')
    if raw is None:
        return []
    scripts = scripts_from(json.loads(raw))
    if len(scripts) != 4 or any(script['command'] not in (wanted, *SUPERSEDED.get(wanted, ()))
                                for script, wanted in zip(scripts, COMMANDS)):
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
    scripts_from(document)
    try:
        return _merge(document, canonical)
    except ValueError as error:
        proposal = copy.deepcopy(document)
        proposal['scripts'] = copy.deepcopy(canonical) + [
            copy.deepcopy(s) for s in scripts_from(document) if s not in canonical]
        diff = ''.join(difflib.unified_diff(
            (json.dumps(document, indent=2) + '\n').splitlines(True),
            (json.dumps(proposal, indent=2) + '\n').splitlines(True),
            fromfile='t3.json (existing)', tofile='t3.json (manual integration proposal)'))
        if not diff:
            diff = ('No canonical file changes; reconcile the conflicting actions manually:\n'
                    + json.dumps(document, indent=2) + '\n')
        raise ValueError(str(error) + '\nConflict: incomplete manual integration proposal; conflicting actions are retained. No overwrite.\n' + diff) from error


def _merge(document, canonical):
    result = copy.deepcopy(document)
    retained = []
    scripts = scripts_from(document)
    earlier = {wanted['command'] for wanted in canonical
               if any(s['name'] == wanted['name'] and s['command'] in SUPERSEDED.get(wanted['command'], ())
                      for s in scripts)}
    for script in scripts:
        found = [s for s in canonical if matches(script, s)]
        if (script['command'] in earlier and script['command'] in RESPELLED
                and all(script['name'] != wanted['name'] for wanted in found)):
            script, found = dict(script, command=RESPELLED[script['command']]), []
        if found:
            if script.keys() - found[0].keys():
                raise ValueError('Preserve extra action fields manually before replacing: ' + script['name'])
            if any(script['command'] not in (wanted['command'], *SUPERSEDED.get(wanted['command'], ()))
                   for wanted in found):
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
             'detail': 'No supported settings-read CLI in T3 0.1.8. Use supported settings UI and project/environment read tools per host; see docs/t3-compatibility.md in sshickles/repo-standard. Effective host state remains pending.'}]
