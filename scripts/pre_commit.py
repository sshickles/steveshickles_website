"""Format and lint the staged files only. Everything else runs while working or in CI."""
import fnmatch
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

from development import ROOT, read_config


def git(*args):
    result = subprocess.run(['git', *args], cwd=ROOT, capture_output=True)
    if result.returncode:
        raise ValueError('Cannot read the staged changes')
    return result.stdout


def names(output):
    return [name for name in output.decode().split('\0') if name]


def backup_directory():
    """Where earlier versions of this hook saved unstaged work while they checked staged content in place."""
    path = Path(git('rev-parse', '--git-path', 'repo-standard-pre-commit').decode().strip())
    return path if path.is_absolute() else Path(ROOT) / path


def leftover(backup):
    """Stop while an earlier version's saved work is still on disk.

    This hook never writes to the working tree, so it has nothing to put back and cannot tell
    which copy the owner wants. Only the owner can compare them.
    """
    if not backup.exists():
        return
    manifest = backup / 'manifest.json'
    try:
        entries = json.loads(manifest.read_text()) if manifest.is_file() else []
        saved = sorted({str(entry[key]) for entry in entries for key in ('name', 'scratch') if entry.get(key)})
    except (ValueError, TypeError, AttributeError, OSError):
        saved = []
    raise ValueError('an earlier commit saved unstaged work in ' + str(backup)
                     + (' for ' + ', '.join(saved) if saved else '')
                     + '. Compare the copies with your files, keep what you want, then delete that folder')


def main():
    dev = read_config(ROOT / '.repo-standard.json')['development']
    if not shutil.which('mise'):
        raise ValueError('mise is missing; run ./scripts/setup')
    if 'preCommit' in dev:
        # A staged-file tool such as lint-staged or Biome selects and restages the files itself.
        return subprocess.call(['mise', 'exec', '--', *dev['preCommit']], cwd=ROOT,
                               env={**os.environ, 'MISE_AUTO_INSTALL': '0'})
    leftover(backup_directory())
    staged = names(git('diff', '--cached', '--name-only', '--diff-filter=ACMR', '-z'))
    checked = [name for name in staged if any(
        fnmatch.fnmatchcase(name, glob) or fnmatch.fnmatchcase(Path(name).name, glob)
        for check in dev['fileChecks'] if check.get('passFiles', True) for glob in check['include'])]
    # The checks read the working tree and the hook writes nothing to it, so no save can be lost
    # to a commit. A partly staged file is therefore checked with its unstaged work included; CI
    # checks the committed content.
    unstaged = set(names(git('diff', '--name-only', '-z')))
    partial = [name for name in checked if name in unstaged]
    if partial:
        print('pre-commit: partly staged, so checked as they stand in the working tree: '
              + ', '.join(partial), file=sys.stderr)
    from changed_tests import file_checks
    return file_checks(ROOT, dev['fileChecks'], checked, whole=False)


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (ValueError, OSError, KeyError, TypeError) as error:
        sys.exit(f'pre-commit: {error}')
