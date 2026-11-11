#!/usr/bin/env bash
# Explicit live-settings entry point. Requires an owner-approved batch reference.
set -euo pipefail
exec python3 "$(dirname "$0")/scripts/repository.py" configure "$@"
