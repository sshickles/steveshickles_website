#!/usr/bin/env python3
"""Expose the pinned lint executable as the static stack's setup artifact."""
from pathlib import Path
import shutil
import subprocess
import tomllib

root = Path(__file__).resolve().parent.parent
expected = tomllib.loads((root / 'mise.toml').read_text())['tools']['github:rhysd/actionlint']
source = shutil.which('actionlint')
if not source:
    raise SystemExit('actionlint is missing; run setup through mise')
actual = subprocess.check_output([source, '-version'], text=True).splitlines()[0].strip()
if actual != expected:
    raise SystemExit('actionlint does not match mise.toml')
artifact = root / '.cache/tools/actionlint'
artifact.parent.mkdir(parents=True, exist_ok=True)
if artifact.is_symlink() or artifact.exists():
    artifact.unlink()
artifact.symlink_to(Path(source).resolve())
