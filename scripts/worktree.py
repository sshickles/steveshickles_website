#!/usr/bin/env python3
"""Create manual worktrees outside T3, or fetch the configured task base."""
import argparse
import os
from pathlib import Path
import re
import sys
import subprocess

from development import ROOT, read_config, run
from commands import clean_git_environment


def base(config):
    remote, branch = config["git"]["remote"], config["git"]["baseBranch"]
    # Explicit refspec avoids stale refs when a remote has a restricted fetch mapping.
    ref = f"refs/remotes/{remote}/{branch}"
    run(["git", "fetch", remote, f"+refs/heads/{branch}:{ref}"])
    run(["git", "rev-parse", "--verify", f"{ref}^{{commit}}"])
    return ref


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("branch", nargs="?")
    parser.add_argument("--base", action="store_true", help="Fetch and print configured base without creating a worktree")
    args = parser.parse_args()
    try:
        clean_git_environment(preserve_transport=True)
        caller = subprocess.run(['git', 'rev-parse', '--show-toplevel'],
                                capture_output=True, text=True)
        if caller.returncode == 0 and Path(caller.stdout.strip()).resolve() != ROOT:
            raise ValueError("Worktree helper belongs to another repository; run this checkout's own scripts/wt.sh")
        if caller.returncode:
            directory = subprocess.run(['git', 'rev-parse', '--git-dir'], capture_output=True)
            if directory.returncode == 0:
                raise ValueError('Run the worktree helper from its own checkout, not a bare repository or Git directory')
        config = read_config(ROOT / ".repo-standard.json")
        if args.base:
            if args.branch:
                raise ValueError("--base does not take a task branch")
            print(base(config))
            return 0
        if ".t3/worktrees" in str(ROOT) or os.environ.get("T3CODE_WORKTREE_PATH"):
            raise ValueError("Reuse the checkout assigned by T3; manual launcher is for use outside T3")
        if not args.branch or not re.fullmatch(config["conventions"]["branchPattern"], args.branch):
            raise ValueError("Branch must match conventions.branchPattern in .repo-standard.json")
        run(["git", "check-ref-format", "--branch", args.branch])
        path = Path.home() / "worktrees" / config["repository"].replace("/", "--") / args.branch.replace("/", "-")
        if path.exists() or path.resolve().is_relative_to(ROOT):
            raise ValueError("Destination exists or is nested in this checkout; preserve it and choose another task")
        start = base(config)
        path.parent.mkdir(parents=True, exist_ok=True)
        run(["git", "worktree", "add", "-b", args.branch, str(path), start])
        print(f"Worktree ready: {path}\nRun ./scripts/setup there.")
    except (ValueError, RuntimeError, OSError, KeyError, TypeError) as error:
        print(f"worktree: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
