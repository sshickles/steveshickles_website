"""Format and lint the staged files only. Everything else runs while working or in CI."""
import ctypes
import errno
import fnmatch
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import signal
import stat
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
    path = Path(git('rev-parse', '--git-path', 'repo-standard-pre-commit').decode().strip())
    return path if path.is_absolute() else Path(ROOT) / path


NOREPLACE, EXCHANGE = 1, 2


class Unsupported(OSError):
    """This filesystem or platform cannot move files in the one-step ways the hook relies on."""


def move(source, target, flags):
    """renameat2. NOREPLACE moves a file only to a free path; EXCHANGE trades two files. Each is one step."""
    try:
        failed = ctypes.CDLL(None, use_errno=True).renameat2(
            -100, os.fsencode(source), -100, os.fsencode(target), ctypes.c_uint(flags))
    except AttributeError:
        raise Unsupported(errno.ENOSYS, 'renameat2 is not available') from None
    if failed:
        number = ctypes.get_errno()
        if number in (errno.EINVAL, errno.ENOSYS, errno.ENOTSUP):
            raise Unsupported(number, os.strerror(number), str(target))
        raise OSError(number, os.strerror(number), str(target))


def digest(content):
    return hashlib.sha256(content).hexdigest()


def record(backup, entries):
    """Write the manifest in one step, so a reader finds the old one or the new one."""
    pending = backup / 'manifest.json.new'
    pending.write_text(json.dumps(entries))
    os.replace(pending, backup / 'manifest.json')


def spare(backup, index, content):
    """Keep a version that has no place in the working tree. It blocks commits until the owner removes it.

    Only the hook writes in the backup, so the first free name is free. The bytes are complete
    before the spare gets its name, and an earlier spare is never replaced.
    """
    pending = backup / 'spare.new'
    pending.write_bytes(content)
    number = 0
    while (backup / (f'{index}.newer' + (f'.{number}' if number else ''))).exists():
        number += 1
    os.rename(pending, backup / (f'{index}.newer' + (f'.{number}' if number else '')))


def workspace(backup, entries, index):
    """A folder next to the file that only this hook writes to.

    It is on the file's own filesystem, has a random name that is created exclusively, and is
    recorded in the manifest before it exists, so a later run finds whatever a cut-short swap left.
    """
    entry = entries[index]
    target = Path(ROOT) / entry['name']
    if entry.get('scratch') and (Path(ROOT) / entry['scratch']).is_dir():
        return Path(ROOT) / entry['scratch']
    target.parent.mkdir(parents=True, exist_ok=True)
    while True:
        scratch = target.parent / ('.pre-commit-' + secrets.token_hex(8))
        entry['scratch'] = str(scratch.relative_to(ROOT))
        record(backup, entries)
        try:
            scratch.mkdir(mode=0o700)
            return scratch
        except FileExistsError:
            continue


def close(scratch):
    """Remove the hook's folder once it is empty."""
    try:
        scratch.rmdir()
    except OSError:
        pass


def discard(held, expected, keep):
    """Remove a displaced copy. False, and the copy is kept, if it does not hold expected.

    An editor that opened the file before the move can still write through that handle, so the
    copy is read again here rather than trusted from an earlier read.
    """
    content = held.read_bytes()
    if content != expected:
        # Stored before its only other copy goes. If this fails or the run ends here, the copy is
        # still in the folder and the next run keeps it.
        keep(content)
    held.unlink()
    return content == expected


def swap(target, expected, replacement, scratch, keep):
    """Replace a working file only while it still holds expected. None stands for an absent file.

    Reading a file and then writing over it would lose a save made in between. The replacement is
    completed in the hook's folder and traded with the working file in one step, so the path is
    never empty or half-written, and whatever the file held at that instant comes back to the
    folder. A save found there is traded back. False means the file holds newer work; keep stores
    a version that could not stay in the working tree.
    """
    held = scratch / 'held'
    if replacement is not None:
        # Written under another name first: a half-written file is never mistaken for a displaced one.
        (scratch / 'incoming').write_bytes(replacement)
        os.rename(scratch / 'incoming', held)
    try:
        if replacement is None:
            move(target, held, NOREPLACE)
        elif expected is None:
            move(held, target, NOREPLACE)
            return True
        else:
            os.chmod(held, stat.S_IMODE(target.stat().st_mode))
            move(held, target, EXCHANGE)
    except FileNotFoundError:
        # Deleted by its owner after the caller read it. It stays deleted.
        held.unlink(missing_ok=True)
        return replacement is None
    except FileExistsError:
        # Created by someone after the caller found it absent. That file is newer work.
        held.unlink()
        return False
    except Unsupported:
        # Nothing was replaced. The caller decides what to do without the move.
        held.unlink(missing_ok=True)
        raise
    found = held.read_bytes()
    if found == expected:
        return discard(held, expected, keep)
    # A save made after the caller read the file. It goes back to its place.
    try:
        move(held, target, NOREPLACE if replacement is None else EXCHANGE)
    except (FileNotFoundError, FileExistsError):
        pass  # The path was deleted or taken in the meantime, so the save stays in the folder.
    if held.is_file():
        # The replacement on its way back out, the save that could not return, or a second save.
        discard(held, replacement, keep)
    return False


def heal(entry, ours, keep):
    """Clear what a cut-short swap left in the hook's folder, before anything else looks at the file.

    The working path is never empty during a swap, so nothing needs to go back. The folder holds
    the replacement on its way in or the displaced copy on its way out. Both are content the
    backup or the index already has, unless an editor saved in between; that version is kept.
    """
    if not entry.get('scratch'):
        return
    scratch = Path(ROOT) / entry['scratch']
    (scratch / 'incoming').unlink(missing_ok=True)  # Never complete, never the working file.
    held = scratch / 'held'
    if held.is_file():
        content = held.read_bytes()
        if not ours(content):
            keep(content)
        held.unlink()
    close(scratch)


def restore(backup):
    """Put unstaged work back from the backup.

    A file that no longer holds its staged content was edited while the checks ran, or after a
    killed run. That is newer work: it is left alone, its saved copy stays in the backup, and the
    commit stops so the owner can compare the two. Every other file is put back first. A version
    kept as spare stops every later commit too, until the owner removes the backup.
    """
    manifest = backup / 'manifest.json'
    entries = json.loads(manifest.read_text()) if manifest.is_file() else []
    edited = []
    for index, entry in enumerate(entries):
        target = Path(ROOT) / entry['name']
        work = None if entry['missing'] else (backup / str(index)).read_bytes()

        def ours(content, work=work, entry=entry):
            return content == work or digest(content) == entry['staged']

        def keep(content, index=index):
            spare(backup, index, content)

        heal(entry, ours, keep)
        current = target.read_bytes() if target.is_file() else None
        changed = False
        if current != work:  # Otherwise it was already put back, or never replaced.
            changed = current is None or digest(current) != entry['staged']
            if not changed:
                scratch = workspace(backup, entries, index)
                try:
                    changed = not swap(target, current, work, scratch, keep)
                except Unsupported:
                    # Only a backup from an older hook can be here: this one stages nothing it cannot trade back.
                    raise ValueError('unstaged work for ' + entry['name'] + ' is saved in ' + str(backup)
                                     + ', and this filesystem cannot put it back in one step. Copy it '
                                     'back by hand, then delete that folder') from None
                finally:
                    close(scratch)
        if changed or any(backup.glob(f'{index}.newer*')):
            edited.append(entry['name'])
    if edited:
        raise ValueError('a commit saved unstaged work in ' + str(backup) + ', and ' + ', '.join(edited)
                         + ' changed while it ran. Compare the copies, keep what you want, '
                         'then delete that folder')
    shutil.rmtree(backup, ignore_errors=True)


def staged_content(backup, partial):
    """Put the staged version of each partly staged file into place, after saving the working copy to disk.

    False where files cannot be traded in one step. Nothing is replaced then.
    """
    backup.mkdir(parents=True)
    entries, staged, work = [], {}, {}
    for index, name in enumerate(partial):
        target = Path(ROOT) / name
        staged[name] = git('show', ':' + name)
        work[name] = target.read_bytes() if target.is_file() else None
        entries.append({'name': name, 'missing': work[name] is None, 'staged': digest(staged[name])})
        if work[name] is not None:
            (backup / str(index)).write_bytes(work[name])
    # The manifest is written last: until it exists nothing has been replaced, so there is nothing to recover.
    record(backup, entries)
    for index, name in enumerate(partial):
        scratch = workspace(backup, entries, index)
        try:
            replaced = swap(Path(ROOT) / name, work[name], staged[name], scratch,
                            lambda content, index=index: spare(backup, index, content))
        except Unsupported:
            restore(backup)
            return False
        if not replaced:
            # A save made after the copy above was taken. restore reports it and keeps every version.
            raise ValueError(name + ' changed while the commit was starting')
        close(scratch)
    return True


def main():
    dev = read_config(ROOT / '.repo-standard.json')['development']
    if not shutil.which('mise'):
        raise ValueError('mise is missing; run ./scripts/setup')
    if 'preCommit' in dev:
        # A staged-file tool such as lint-staged or Biome selects and restages the files itself.
        return subprocess.call(['mise', 'exec', '--', *dev['preCommit']], cwd=ROOT,
                               env={**os.environ, 'MISE_AUTO_INSTALL': '0'})
    backup = backup_directory()
    restore(backup)
    staged = names(git('diff', '--cached', '--name-only', '--diff-filter=ACMR', '-z'))
    checked = [name for name in staged if any(
        fnmatch.fnmatchcase(name, glob) or fnmatch.fnmatchcase(Path(name).name, glob)
        for check in dev['fileChecks'] if check.get('passFiles', True) for glob in check['include'])]
    # A partly staged file differs between the index and the working tree, or is gone from the
    # working tree. Its staged content is checked in place and the unstaged work is put back.
    unstaged = set(names(git('diff', '--name-only', '-z')))
    # A symbolic link is checked as it stands: replacing it would turn it into a regular file.
    partial = [name for name in checked if name in unstaged and not (Path(ROOT) / name).is_symlink()]
    from changed_tests import file_checks

    def interrupted(signum, frame):
        raise SystemExit(128 + signum)
    previous = {signum: signal.signal(signum, interrupted) for signum in (signal.SIGTERM, signal.SIGHUP)}
    try:
        if partial and not staged_content(backup, partial):
            print('pre-commit: this filesystem cannot trade two files in one step, so partly staged '
                  'files are checked as they stand in the working tree', file=sys.stderr)
        return file_checks(ROOT, dev['fileChecks'], checked, whole=False)
    finally:
        restore(backup)
        for signum, handler in previous.items():
            signal.signal(signum, handler)


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (ValueError, OSError, KeyError, TypeError) as error:
        sys.exit(f'pre-commit: {error}')
