"""Optional portable adapter to the operator-installed Halo workspace client.

The host decides enrollment and infrastructure. Repository setup never installs
services, changes model state, selects an endpoint or grants indexing access.
"""
from pathlib import Path
import subprocess


def prepare(root, doctor=False, home=None):
    home = Path.home() if home is None else Path(home)
    client = home / ".local/bin/halo-workspace"
    required = home / ".config/halo-codebase/required"
    if not client.is_file():
        if required.exists():
            raise RuntimeError("Halo is required on this host but its client is missing; repair host onboarding")
        print("Halo: host not configured; local setup continues. See docs/halo.md for enrollment.")
        return
    try:
        result = subprocess.run([str(client), "doctor" if doctor else "ready"],
                                cwd=root, check=False, stdin=subprocess.DEVNULL,
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                timeout=600)
    except subprocess.TimeoutExpired:
        raise RuntimeError("Halo readiness timed out; repair host setup before the first turn") from None
    except OSError:
        raise RuntimeError("Halo client cannot run; repair host onboarding") from None
    if result.returncode:
        raise RuntimeError("Halo readiness failed; enroll this repository or repair host setup before the first turn")
