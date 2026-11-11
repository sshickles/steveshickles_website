#!/usr/bin/env bash
set -euo pipefail
script="$(python3 -c 'from pathlib import Path; import sys; print(Path(sys.argv[1]).resolve())' "${BASH_SOURCE[0]}")"
exec python3 -B "$(dirname "$script")/worktree.py" "$@"
