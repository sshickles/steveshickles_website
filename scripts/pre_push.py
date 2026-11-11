"""Validate destination refs before running the common check command."""
import json
import os
import subprocess
import sys
from development import ROOT


def repository_checks(root):
    directory = root / '.githooks/pre-push.d'
    if not directory.exists() and not directory.is_symlink():
        return []
    if directory.is_symlink() or not directory.is_dir():
        raise ValueError('Expected a repository-owned directory: .githooks/pre-push.d')
    checks = sorted(directory.iterdir())
    for check in checks:
        if check.is_symlink() or not check.is_file() or not os.access(check, os.X_OK):
            raise ValueError(f'Repository pre-push check must be a regular executable file: {check.name}')
    return checks


def default_branch(remote):
    config = ROOT / '.repo-standard.json'
    if config.exists():
        branch = json.loads(config.read_text()).get('git', {}).get('baseBranch')
        if branch:
            return branch
    result = subprocess.run(['git', 'symbolic-ref', f'refs/remotes/{remote}/HEAD'],
                            cwd=ROOT, text=True, capture_output=True)
    if result.returncode == 0:
        return result.stdout.strip().removeprefix(f'refs/remotes/{remote}/')
    raise ValueError('Cannot determine protected default branch; configure git.baseBranch or remote HEAD')


def main():
    branch = default_branch(sys.argv[1] if len(sys.argv) > 1 else 'origin')
    refs = sys.stdin.buffer.read()
    for line in refs.splitlines():
        _, _, remote_ref, _ = line.split()
        if remote_ref == ('refs/heads/' + branch).encode():
            raise ValueError('Direct pushes to the default branch are forbidden; open a PR')
    checks = repository_checks(ROOT)
    # The approved contract runs checks on every push, including ref deletions.
    result = subprocess.call([str(ROOT / 'scripts/check')], cwd=ROOT, stdin=subprocess.DEVNULL)
    if result:
        return result
    for check in checks:
        result = subprocess.run([str(check), *sys.argv[1:]], cwd=ROOT, input=refs)
        if result.returncode:
            return result.returncode
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (ValueError, OSError, KeyError, TypeError) as error:
        sys.exit(f'pre-push: {error}')
