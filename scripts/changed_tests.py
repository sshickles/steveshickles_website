"""Conservative affected-test selection for local pre-push checks only."""
import fnmatch
import math
import os
import shlex
from pathlib import Path
import subprocess

# Match basenames at every depth as well as repository-relative paths.
SHARED_GLOBS = (
    '*.lock', '*lock*.json', '*lock*.yaml', '*lock*.yml', 'package.json',
    'pyproject.toml', 'requirements*.txt', 'Pipfile*', 'setup.*', 'tox.ini',
    'pytest.ini', '.coveragerc', 'conftest.py', '*config*', '*setup*', '*Setup*',
    'vitest.*', 'vite.*', '.*rc', '.*rc.*', '.env*', '.pnpmfile.*', '.pnp.*',
    'bun.lockb', 'npm-shrinkwrap.json', 'pnpm-workspace.yaml', 'turbo.json', 'nx.json',
    'requirements*.in', 'deno.json*', 'rust-toolchain*',
    'mise.*', '.mise.*', '.tool-versions', '.python-version', '.node-version',
    '.nvmrc', '.repo-standard*.json', '.github/workflows/*', '.githooks/*',
    'scripts/*', 'policy/*',
)
JS_SUFFIXES = {'.js', '.jsx', '.ts', '.tsx', '.mjs', '.cjs', '.mts', '.cts'}
DOCUMENTATION_GLOBS = ('README*', 'CHANGELOG*', 'LICENSE*', 'COPYING*',
                       'AUTHORS*', 'CONTRIBUTING*', 'docs/**')


def git(root, *args):
    result = subprocess.run(['git', *args], cwd=root, capture_output=True, text=True)
    if result.returncode:
        raise ValueError('Git history unavailable')
    return result.stdout.rstrip('\n')


def changed_files(root, commits):
    """Union changes from each pushed commit's merge-base, including tracked edits."""
    from pre_push import default_branch
    try:
        if git(root, 'rev-parse', '--is-shallow-repository') == 'true':
            return None, 'shallow history'
        branch = default_branch('origin')
        remote = 'refs/remotes/origin/' + branch
        git(root, 'rev-parse', '--verify', remote + '^{commit}')
        head = git(root, 'rev-parse', 'HEAD')
        commits = commits or [head]  # Deletion-only pushes still validate the checkout.
        files = set()
        for commit in commits:
            tip = git(root, 'rev-parse', '--verify', commit + '^{commit}')
            if tip != head:
                return None, 'pushed commit differs from checked-out HEAD'
            base = git(root, 'merge-base', remote, tip)
            # No rename detection: both old and new names participate in fallbacks.
            for revisions in ((base, tip), (tip,)):
                names = git(root, 'diff', '--name-only', '-z', '--no-renames', *revisions, '--')
                files.update(filter(None, names.split('\0')))
        return sorted(files), 'changes since merge-base with ' + remote
    except (ValueError, OSError):
        return None, 'base cannot be resolved'


def vitest_options():
    workers = os.environ.get('VITEST_MAX_WORKERS')
    if workers is None:
        workers = str(max(1, math.floor(len(os.sched_getaffinity(0)) - os.getloadavg()[0])))
    timeout = os.environ.get('REPO_STANDARD_TEST_TIMEOUT', '15000')
    for name, value in (('VITEST_MAX_WORKERS', workers), ('REPO_STANDARD_TEST_TIMEOUT', timeout)):
        if not value.isdecimal() or int(value) < 1:
            raise ValueError(name + ' must be a positive integer')
    return ['--maxWorkers', workers, '--testTimeout', timeout]


def vitest_arguments(arguments, *, related=False):
    """Replace hook limits without duplicate flags or partial-suite coverage gates."""
    result = []
    index = 0
    minimum = False
    while index < len(arguments):
        argument = arguments[index]
        name, separator, _ = argument.partition('=')
        index += 1
        if name in ('--maxWorkers', '--max-workers', '--testTimeout', '--test-timeout',
                    '--minWorkers', '--min-workers'):
            minimum |= name in ('--minWorkers', '--min-workers')
            if not separator:
                index += 1
        elif related and name in ('--coverage', '--coverage.enabled'):
            if not separator and index < len(arguments) and arguments[index] in ('true', 'false'):
                index += 1
        else:
            result.append(argument)
    if minimum:
        result += ['--minWorkers', '1']
    if related:
        result += ['--coverage.enabled=false']
    return [*result, *vitest_options()]


def pytest_requires_full(root, command):
    """Keep coverage gates on their full suite, including configured addopts."""
    arguments = [*command, *shlex.split(os.environ.get('PYTEST_ADDOPTS', ''))]
    if any(arg.startswith(('--cov', '--rootdir', '--config-file', '-c')) for arg in arguments):
        return True
    if any(not arg.startswith('-') and (root / arg.split('::', 1)[0]).exists()
           for arg in arguments[1:]):
        return True
    names = {'pytest.ini', '.pytest.ini', 'pytest.toml', '.pytest.toml',
             'tox.ini', 'setup.cfg', 'pyproject.toml'}
    paths = {root / name for name in names}
    paths.update(root / name for name in git(root, 'ls-files', '-z').split('\0')
                 if Path(name).name in names)
    for path in paths:
        if path.is_file():
            text = path.read_text()
            if any(setting in text for setting in ('--cov', 'testpaths', 'python_files',
                                                   'python_classes', 'python_functions',
                                                   'norecursedirs', '--ignore', '--deselect')):
                return True
    return False


def unittest_scope(root, full, runner):
    """Resolve discovery's import root; reject options we cannot preserve safely."""
    if full[:len(runner)] != runner:
        raise ValueError('unittest command differs from the mapping')
    if any(arg.startswith('-') and not arg.startswith('--') and any(flag in arg[1:] for flag in 'IE')
           for arg in runner[:-2]):
        raise ValueError('unittest interpreter options ignore the selected import path')
    arguments = full[len(runner):]
    if arguments[:1] != ['discover']:
        raise ValueError('unittest selection requires discover')
    start, top, pattern, options = '.', None, 'test*.py', []
    index = 1
    while index < len(arguments):
        arg = arguments[index]
        index += 1
        key, equals, value = arg.partition('=')
        if key in ('-s', '--start-directory', '-t', '--top-level-directory', '-p', '--pattern'):
            if not equals:
                if index == len(arguments):
                    raise ValueError('missing unittest discovery option value')
                value = arguments[index]
                index += 1
            if key in ('-s', '--start-directory'):
                start = value
            elif key in ('-t', '--top-level-directory'):
                top = value
            else:
                pattern = value
        elif arg in ('-v', '--verbose', '-q', '--quiet', '-f', '--failfast',
                     '-b', '--buffer', '-c', '--catch'):
            options.append(arg)
        else:
            raise ValueError('unsupported unittest discovery option')
    start = (root / start).resolve()
    top = (root / top).resolve() if top is not None else start
    if not start.is_relative_to(top) or not top.is_relative_to(root) or not start.is_dir():
        raise ValueError('unittest discovery paths are outside the checkout or missing')
    # discover prepends top to sys.path, while python -m leaves the checkout
    # first. Collisions in helpers as well as selected modules make that unsafe.
    if top != root:
        for entry in top.iterdir():
            if entry.suffix == '.py' or (entry.is_dir() and (entry / '__init__.py').is_file()):
                module = entry.stem if entry.is_file() else entry.name
                if (root / module).exists() or (root / (module + '.py')).exists():
                    raise ValueError('unittest import is shadowed at the checkout root')
    # Discovery calls load_tests hooks which direct module loading would bypass.
    for name in filter(None, git(root, 'ls-files', '--cached', '--others', '--exclude-standard', '-z', '--', '*__init__.py').split('\0')):
        package = root / name
        if not package.is_file():
            continue
        if package.is_relative_to(start) or package.parent in start.parents or package.parent == start:
            if 'load_tests' in package.read_text():
                raise ValueError('unittest discovery uses load_tests')
    return start, top, pattern, options


def unittest_modules(root, full, runner, selected):
    start, top, pattern, options = unittest_scope(root, full, runner)
    modules = []
    for name in sorted(selected):
        path = (root / name).resolve()
        if not path.is_relative_to(start) or not fnmatch.fnmatchcase(path.name, pattern):
            raise ValueError('changed test is outside unittest discovery')
        if 'load_tests' in path.read_text():
            raise ValueError('unittest test module uses load_tests')
        relative = path.relative_to(top).with_suffix('')
        if not all(part.isidentifier() for part in relative.parts):
            raise ValueError('unittest module name is not importable')
        for parent in path.parents:
            if parent == top:
                break
            if not (parent / '__init__.py').is_file():
                raise ValueError('unittest package is missing __init__.py')
        modules.append('.'.join(relative.parts))
    return [*runner, *options, *modules]


def select_tests(root, config, files, reason):
    root = Path(root).resolve()
    dev = config['development']
    mapping = dev.get('changedTestCommand')
    full = list(config['testCommand'])
    kind = mapping['kind'] if mapping else None
    # An explicit mapping supplies a direct runner so flags never target a wrapper.
    if kind == 'vitest':
        full = vitest_arguments(full)
    def fallback(why):
        return full, 'full tests: ' + why
    if files is None:
        return fallback(reason)
    shared = (*SHARED_GLOBS, *dev.get('sharedInfrastructureGlobs', []))
    for name in files:
        if any(fnmatch.fnmatchcase(name, glob) or fnmatch.fnmatchcase(Path(name).name, glob)
               for glob in shared):
            return fallback('shared infrastructure changed: ' + name)
    if not mapping:
        return fallback('no affected-test mapping configured')
    suffixes = JS_SUFFIXES if kind == 'vitest' else {'.py'}
    for name in files:
        if (Path(name).suffix not in suffixes
                and not any(fnmatch.fnmatchcase(name, glob) for glob in DOCUMENTATION_GLOBS)):
            return fallback('unclassified test input changed: ' + name)
    if kind == 'vitest':
        relevant = [name for name in files if Path(name).suffix in JS_SUFFIXES]
        if any(not (root / name).is_file() for name in relevant):
            return fallback('source or test file deleted')
        if not relevant:
            return [], 'no changed relevant files; no tests'
        options = config['testCommand'][len(mapping['command']) + 1:]
        if any(not arg.startswith('-') or arg == '--' for arg in options):
            return fallback('Vitest positional filters or separate option values require the full command')
        return [*mapping['command'], 'related', *(str(root / name) for name in relevant),
                '--run', '--passWithNoTests',
                *vitest_arguments(options, related=True)], 'affected Vitest tests: ' + reason
    selected = set()
    for name in files:
        path = Path(name)
        if path.suffix != '.py':
            continue
        if not (root / path).is_file():
            return fallback('Python source or test file deleted')
        if path.name.startswith('test_') or path.name.endswith('_test.py'):
            selected.add(name)
            continue
        # Source modules can affect callers' tests too; naming alone cannot prove
        # that a matching test covers all dependents. Keep that case conservative.
        return fallback('Python module dependencies require full coverage: ' + name)
    if not selected:
        return [], 'no changed relevant files; no tests'
    try:
        if kind == 'pytest' and pytest_requires_full(root, config['testCommand']):
            return fallback('pytest coverage, discovery or custom configuration requires the full command')
        # Searching tracked Python text also catches literal dynamic imports and
        # relative imports without needing to infer the destination's sys.path.
        modules = {Path(name).stem for name in selected}
        for name in filter(None, git(root, 'ls-files', '--cached', '--others', '--exclude-standard', '-z', '--', '*.py').split('\0')):
            if name in selected or not (root / name).is_file():
                continue
            text = (root / name).read_text()
            if any(module in text for module in modules):
                return fallback('changed test module referenced by ' + name)
    except (ValueError, OSError, UnicodeError):
        return fallback('cannot determine Python test-module dependents')
    if kind == 'unittest':
        try:
            command = unittest_modules(root, full, mapping['command'], selected)
        except (ValueError, OSError, UnicodeError) as error:
            return fallback(str(error))
        return command, 'changed unittest modules: ' + reason
    return [*mapping['command'], *('./' + name for name in sorted(selected))], 'changed pytest files: ' + reason


def run(root, config, commits):
    root = Path(root).resolve()
    files, reason = changed_files(root, commits)
    command, message = select_tests(root, config, files, reason)
    print('Pre-push: ' + message, flush=True)
    if not command:
        return 0
    environment = {**os.environ, 'MISE_AUTO_INSTALL': '0'}
    mapping = config['development'].get('changedTestCommand')
    if mapping and mapping['kind'] == 'unittest' and message.startswith('changed unittest modules:'):
        try:
            _, top, _, _ = unittest_scope(root, config['testCommand'], mapping['command'])
        except (ValueError, OSError, UnicodeError):
            command = list(config['testCommand'])
            print('Pre-push: full tests: unittest import scope became unavailable', flush=True)
        else:
            environment['PYTHONPATH'] = str(top) + (os.pathsep + environment['PYTHONPATH']
                                                    if environment.get('PYTHONPATH') else '')
    if mapping and mapping['kind'] == 'vitest':
        workers = command[command.index('--maxWorkers') + 1]
        # Vitest 3 pool-specific bounds take precedence over maxWorkers. Newer
        # versions ignore these legacy variables and use the CLI limit instead.
        for pool in ('THREADS', 'FORKS'):
            environment['VITEST_MIN_' + pool] = '1'
            environment['VITEST_MAX_' + pool] = workers
    return subprocess.call(['mise', 'exec', '--', *command], cwd=root, env=environment)
