"""Common checkout commands, with stack-specific implementations underneath."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

from development import ROOT, read_config, provision


def require_tool(name):
    if not shutil.which(name):
        raise ValueError(f'Install {name} on the host first; see docs/setup.md')


def clean_git_environment():
    require_tool('git')
    result = subprocess.run(['git', 'rev-parse', '--local-env-vars'], capture_output=True, text=True)
    for name in result.stdout.splitlines():
        os.environ.pop(name, None)


def review():
    parser = argparse.ArgumentParser(description='Review the complete task diff; see docs/agents/review-checklist.md')
    parser.add_argument('--base')
    args = parser.parse_args()
    config = read_config(ROOT / '.repo-standard.json')
    base = args.base or config['git']['remote'] + '/' + config['git']['baseBranch']
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
        result = subprocess.run([*runner, 'review', '--deep', '--agent', '--gate', 'info', '--include-untracked', '--base', base, '-c', *instructions], cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
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
        if len(sys.argv) != 1:
            raise ValueError(f'{name} takes no arguments')
        require_tool('mise')
        if name == 'test':
            config = read_config(ROOT / '.repo-standard.json')
            return subprocess.call(['mise', 'exec', '--', *config['testCommand']],
                                   env={**os.environ, 'MISE_AUTO_INSTALL': '0'})
        from repository import validate
        validate(ROOT)
        config = read_config(ROOT / '.repo-standard.json')
        result = subprocess.run([str(ROOT / 'scripts/test')])
        if result.returncode:
            return result.returncode
        for command in config['validation']:
            result = subprocess.run(['mise', 'exec', '--', *command], env={**os.environ, 'MISE_AUTO_INSTALL': '0'})
            if result.returncode:
                return result.returncode
        print('All local checks passed.')
        return 0
    except (ValueError, OSError, RuntimeError, KeyError, TypeError) as error:
        print(f'{name}: {error}', file=sys.stderr)
        if name == 'review':
            fallback()
        return 1
