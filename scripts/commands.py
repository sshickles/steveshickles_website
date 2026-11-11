"""Common checkout commands, with stack-specific implementations underneath."""
import argparse
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import threading

from development import ROOT, read_config, provision

REVIEW_HEARTBEAT_SECONDS = 30
REVIEW_TIMEOUT_SECONDS = 30 * 60


def require_tool(name):
    if not shutil.which(name):
        raise ValueError(f'Install {name} on the host first; see docs/setup.md')


def clean_git_environment(*, preserve_transport=False):
    require_tool('git')
    result = subprocess.run(['git', 'rev-parse', '--local-env-vars'], capture_output=True, text=True)
    if result.returncode:
        raise ValueError('Cannot identify inherited Git repository variables')
    local_names = result.stdout.splitlines()
    transport = []
    if preserve_transport:
        config_env = {key: value for key, value in os.environ.items()
                      if key not in local_names or key in ('GIT_CONFIG_COUNT', 'GIT_CONFIG_PARAMETERS')}
        # Let Git decode both config environment formats; never print values.
        result = subprocess.run(['git', 'config', '--null', '--list', '--show-scope'],
                                cwd=ROOT, env=config_env, capture_output=True, text=True)
        if result.returncode:
            raise ValueError('Cannot read Git transport configuration safely')
        fields = result.stdout.split('\0')
        for scope, entry in zip(fields[0::2], fields[1::2]):
            key, separator, value = entry.partition('\n')
            if not separator:
                value = 'true'
            lower = key.lower()
            if scope == 'command' and (
                lower.startswith(('http.', 'credential.', 'protocol.', 'ssh.'))
                or lower in ('core.sshcommand', 'core.gitproxy')
                or lower.startswith('url.') and lower.endswith(('.insteadof', '.pushinsteadof'))
            ):
                transport.append((key, value))
    for name in local_names:
        os.environ.pop(name, None)
    if transport:
        os.environ['GIT_CONFIG_COUNT'] = str(len(transport))
        for index, (key, value) in enumerate(transport):
            os.environ[f'GIT_CONFIG_KEY_{index}'] = key
            os.environ[f'GIT_CONFIG_VALUE_{index}'] = value


def run_review(argv):
    def terminate(signum, frame):
        raise SystemExit(128 + signum)
    previous = {}
    try:
        for signum in (signal.SIGTERM, signal.SIGHUP):
            previous[signum] = signal.signal(signum, terminate)
        with subprocess.Popen(argv, cwd=ROOT, text=True, stdout=subprocess.PIPE,
                              stderr=subprocess.STDOUT, start_new_session=True) as process:
            try:
                output, _ = process.communicate(timeout=REVIEW_TIMEOUT_SECONDS)
            except BaseException:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                # A detached descendant may still hold the pipe. Discard output on
                # failure instead of waiting for that unrelated session to close it.
                process.stdout.close()
                raise
            return subprocess.CompletedProcess(argv, process.returncode, output)
    finally:
        for signum, handler in previous.items():
            signal.signal(signum, handler)

def review():
    parser = argparse.ArgumentParser(description='Review the complete task diff; see docs/agents/review-checklist.md')
    parser.add_argument('--base')
    args = parser.parse_args()
    config = read_config(ROOT / '.repo-standard.json')
    base = args.base or 'refs/remotes/' + config['git']['remote'] + '/' + config['git']['baseBranch']
    auto = Path.home() / '.local/bin/cr-auto'
    runner = [str(auto)] if auto.is_file() and os.access(auto, os.X_OK) else None
    if runner is None and shutil.which('cr-as'):
        profiles = {'sshickles': 'ss', 'bluebonnet-logic': 'bbl', 'prison-professors': 'pp',
                    'release-strategy-pro': 'rsp', 'white-collar-advice': 'wca'}
        profile = profiles.get(config['repository'].split('/')[0])
        if profile:
            runner = ['cr-as', profile]
    if runner:
        # Gate at info: every reported severity makes the CLI exit nonzero.
        instructions = ['AGENTS.md', '.coderabbit.yaml', 'docs/agents/policy.md',
                        'docs/agents/repository.md', 'docs/agents/review-checklist.md']
        print('Starting CodeRabbit review against ' + base + '; waiting for a complete gated result.', flush=True)
        stopped = threading.Event()
        def heartbeat():
            while not stopped.wait(REVIEW_HEARTBEAT_SECONDS):
                print('CodeRabbit review still running; gate pending.', flush=True)
        progress = threading.Thread(target=heartbeat, daemon=True)
        progress.start()
        try:
            result = run_review([*runner, 'review', '--deep', '--agent', '--gate', 'info', '--include-untracked', '--base', base, '-c', *instructions])
        except subprocess.TimeoutExpired as error:
            raise RuntimeError(f'CodeRabbit review timed out after {REVIEW_TIMEOUT_SECONDS} seconds; gate failed.') from error
        finally:
            stopped.set()
            progress.join()
        print(result.stdout or '', end='')
        if result.returncode:
            print(f'CodeRabbit review failed (exit {result.returncode}). Do not attempt browser login.', file=sys.stderr)
            fallback()
            return result.returncode
        completed = None
        for line in (result.stdout or '').splitlines():
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(event, dict) and event.get('type') == 'complete':
                completed = event
        if (not completed or completed.get('outcome') != 'completed'
                or completed.get('findings') != 0
                or completed.get('gate', {}).get('status') != 'passed'):
            print('CodeRabbit did not certify a clean complete review. Inspect warnings or incomplete output.', file=sys.stderr)
            fallback()
            return 1
        print('CodeRabbit review completed with no findings and a passing gate.')
        return 0
    print('CodeRabbit unavailable: no configured cr-auto or cr-as runner.', file=sys.stderr)
    fallback()
    return 1


def fallback():
    print('Independent review required: follow docs/agents/review-checklist.md. Use a reviewer who did not implement the change, with a distinct base model where available. Record the reviewed diff, findings, fixes and any same-model fallback. This command cannot certify that external result.', file=sys.stderr)


def main(name):
    try:
        clean_git_environment()
        os.chdir(ROOT)
        if name == 'setup':
            parser = argparse.ArgumentParser()
            parser.add_argument('--doctor', action='store_true')
            args = parser.parse_args()
            provision(ROOT, args.doctor)
            return 0
        if name == 'review':
            return review()
        parser = argparse.ArgumentParser()
        if name == 'check':
            parser.add_argument('--pre-push', nargs='*', metavar='COMMIT')
        args = parser.parse_args()
        hook = name == 'check' and args.pre_push is not None
        require_tool('mise')
        if name == 'test':
            config = read_config(ROOT / '.repo-standard.json')
            return subprocess.call(['mise', 'exec', '--', *config['testCommand']],
                                   env={**os.environ, 'MISE_AUTO_INSTALL': '0'})
        from repository import validate
        validate(ROOT)
        config = read_config(ROOT / '.repo-standard.json')
        if not hook:
            result = subprocess.run([str(ROOT / 'scripts/test')])
            if result.returncode:
                return result.returncode
        for command in config['validation']:
            if hook and command == config['testCommand']:
                continue
            result = subprocess.run(['mise', 'exec', '--', *command], env={**os.environ, 'MISE_AUTO_INSTALL': '0'})
            if result.returncode:
                return result.returncode
        if hook:
            from changed_tests import run
            result = run(ROOT, config, args.pre_push)
            if result:
                return result
        print('All local checks passed.')
        return 0
    except (ValueError, OSError, RuntimeError, KeyError, TypeError) as error:
        print(f'{name}: {error}', file=sys.stderr)
        if name == 'review':
            fallback()
        return 1
