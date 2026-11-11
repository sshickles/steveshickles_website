#!/usr/bin/env python3
"""Checkout-local provisioning and read-only diagnosis. No remote configuration."""
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

try:
    import tomllib
except ImportError:
    sys.exit("setup: Python 3.11+ is required")

ROOT = Path(__file__).resolve().parent.parent
VERSION_PROBES = {
    'actionlint': ['actionlint', '-version'],
    'go': ['go', 'version'],
    'rust': ['rustc', '--version'],
}


def read_config(path):
    config = json.loads(Path(path).read_text())
    if not isinstance(config, dict) or config.get("version") != 2:
        raise ValueError("Use configuration version 2; see docs/setup.md for migration")
    for key in ("repository", "profile", "git", "validation", "integrations", "review", "development", "conventions", "ciChecks", "testCommand"):
        if key not in config:
            raise ValueError(f"Missing required configuration: {key}")
    for key in ("git", "integrations", "review", "development", "conventions"):
        if not isinstance(config[key], dict):
            raise ValueError(f"{key} must be an object")
    if not isinstance(config["repository"], str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9-]*/[A-Za-z0-9][A-Za-z0-9_.-]*", config["repository"]):
        raise ValueError("repository must be OWNER/REPO")
    if config["profile"] not in ("nextjs", "custom"):
        raise ValueError("profile must be nextjs or custom (existing/custom template stack)")
    git = config["git"]
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", git.get("remote", "")):
        raise ValueError("git.remote must be an explicit remote name")
    branch = git.get("baseBranch", "")
    if not branch or branch.startswith("-") or subprocess.run(
        ["git", "check-ref-format", "--branch", branch], capture_output=True).returncode:
        raise ValueError("git.baseBranch must be a valid branch")
    if not isinstance(config["validation"], list) or not config["validation"]:
        raise ValueError("validation requires at least one finite local command")
    dev = config["development"]
    if dev.get("environment") not in ("none", "development", "preview", "production"):
        raise ValueError("development.environment must name a documented service environment")
    for key in ("requiredFiles", "localCommands"):
        if not isinstance(dev.get(key), list):
            raise ValueError(f"development.{key} must be an explicit list")
    for name in dev["requiredFiles"]:
        if not isinstance(name, str) or Path(name).is_absolute() or ".." in Path(name).parts:
            raise ValueError("requiredFiles must contain checkout-relative paths")
    # Production pulls and local generation are allowed under the shared policy.
    # Every initializer must be reviewed, idempotent and non-deploying in any environment.
    if dev["localCommands"] and dev["environment"] == "none":
        raise ValueError("Select an environment before enabling localCommands")
    commands = config["validation"] + dev["localCommands"] + [config.get("testCommand")]
    if "dependencies" in dev:
        if not isinstance(dev["dependencies"], dict):
            raise ValueError("development.dependencies must be an object")
        commands = commands + [dev["dependencies"].get("install")]
    for command in commands:
        if not isinstance(command, list) or not command or not all(isinstance(s, str) and s for s in command):
            raise ValueError("Commands must be nonempty argv lists, with no secrets")
        if any(arg in ("--prod", "--run-prod", "deploy") or arg.endswith(":deploy") for arg in command):
            raise ValueError("Setup and validation must not deploy as a side effect")
    integrations = config["integrations"]
    if not isinstance(integrations.get("greptile"), bool) or not (
        integrations.get("deploymentCheck") is None or isinstance(integrations.get("deploymentCheck"), str)
        and integrations["deploymentCheck"].strip()
    ) or "deploymentCheck" not in integrations:
        raise ValueError("Specify integrations.greptile (boolean) and deploymentCheck (name or null)")
    if not isinstance(config["review"].get("coderabbit"), bool):
        raise ValueError("review.coderabbit must be a boolean")
    if "allowAutoMerge" in config["review"]:
        raise ValueError("Remove obsolete review.allowAutoMerge; native auto-merge is standard")
    checks = config.get("ciChecks")
    if not isinstance(checks, list) or not checks or not all(
        isinstance(c, dict) and isinstance(c.get("context"), str) and c["context"].strip()
        for c in checks
    ):
        raise ValueError("ciChecks must name the repository's actual CI checks")
    conventions = config["conventions"]
    for key in ("branchPattern", "issueReadiness", "claiming"):
        if not isinstance(conventions.get(key), str) or not conventions[key].strip():
            raise ValueError(f"conventions.{key} is required")
    re.compile(conventions["branchPattern"])
    return config


def run(command, root=ROOT):
    # Child output can contain environment values. Never echo it or argv on failure.
    result = subprocess.run(command, cwd=root, capture_output=True, text=True,
                            env={**os.environ, "MISE_AUTO_INSTALL": "0"})
    if result.returncode:
        raise RuntimeError(f"{Path(command[0]).name} failed (exit {result.returncode}); inspect locally with secret-safe logging")
    return result.stdout.strip()


def toolchain(root, config=None):
    tools = tomllib.loads((root / "mise.toml").read_text()).get("tools", {})
    if not tools or any(not isinstance(v, str) or not re.fullmatch(r"\d+\.\d+\.\d+", v) for v in tools.values()):
        raise ValueError("Pin every mise.toml tool to an exact x.y.z version")
    package = root / "package.json"
    if not package.exists():
        config = config or read_config(root / ".repo-standard.json")
        adapter = config["development"].get("dependencies")
        if not isinstance(adapter, dict):
            raise ValueError("Non-Node stacks require development.dependencies with lockfile, install and artifacts")
        install = adapter.get("install")
        if not isinstance(install, list) or not install or not all(isinstance(s, str) and s for s in install):
            raise ValueError("dependencies.install must be a locked-install argv list")
        paths = [adapter.get("lockfile")] + adapter.get("artifacts", [])
        if not adapter.get("artifacts") or any(not isinstance(p, str) or not p or Path(p).is_absolute() or ".." in Path(p).parts for p in paths):
            raise ValueError("dependencies lockfile and artifacts must be nonempty checkout-relative paths")
        if not (root / adapter["lockfile"]).is_file():
            raise ValueError("Missing adapter lockfile; commit it before setup")
        return tools, install
    manager = json.loads(package.read_text()).get("packageManager", "")
    match = re.fullmatch(r"(pnpm|npm|yarn)@(\d+\.\d+\.\d+)(?:\+sha\d+\..+)?", manager)
    if not match or "node" not in tools:
        raise ValueError("Declare node in mise.toml and pinned pnpm, npm or Yarn in package.json.packageManager")
    name, version = match.groups()
    if tools.get(name) != version:
        raise ValueError(f"Pin {name}={version} in mise.toml to match packageManager")
    installs = {"pnpm": ("pnpm-lock.yaml", ["pnpm", "install", "--frozen-lockfile"]),
                "npm": ("package-lock.json", ["npm", "ci"]),
                "yarn": ("yarn.lock", ["yarn", "install", "--immutable"])}
    if name == "yarn" and int(version.split(".")[0]) < 2:
        raise ValueError("Yarn requires version 2+ for immutable installs")
    lock, install = installs[name]
    if not (root / lock).is_file():
        raise ValueError(f"Missing {lock}; commit a lockfile before provisioning")
    return tools, install


def tool_version(output):
    match = re.search(r'\b(?:go|v)?(\d+\.\d+\.\d+)\b', output)
    if not match:
        raise ValueError('Tool returned no semantic version; document a supported version adapter')
    return match.group(1)


def provision(root, doctor=False):
    config = read_config(root / ".repo-standard.json")
    tools, install = toolchain(root, config)
    for executable in ("git", "mise"):
        if not shutil.which(executable):
            raise ValueError(f"Install {executable} on the host first")
    if Path(run(["git", "rev-parse", "--show-toplevel"], root)).resolve() != root:
        raise ValueError("Setup script must live in the checkout it provisions")
    dev = config["development"]
    hooks = subprocess.run(["git", "config", "--get", "core.hooksPath"], cwd=root, capture_output=True, text=True)
    if hooks.stdout.strip() not in ("", ".githooks"):
        raise ValueError("Existing core.hooksPath differs; integrate hooks manually before setup")
    if not (root / ".githooks/pre-push").is_file():
        raise ValueError("Missing .githooks/pre-push; adopt the hook before setup")
    # Check selection and artifacts before any command, including dependency scripts.
    missing = [p for p in dev["requiredFiles"] if not (root / p).is_file()]
    if missing:
        raise ValueError("Required local artifacts missing; pull the selected environment from its cloud store: " + ", ".join(missing))
    if not doctor:
        print("Installing pinned tools and locked dependencies", flush=True)
        run(["mise", "install"], root)
    for name, expected in tools.items():
        short = name.split(':')[-1].split('/')[-1]
        probe = VERSION_PROBES.get(short, [short, '--version'])
        output = run(['mise', 'exec', '--', *probe], root)
        if not output:
            raise ValueError(f"{name} returned no version; check the installed tool")
        actual = tool_version(output)
        if actual != expected:
            raise ValueError(f"{name} version mismatch; run mise install in this checkout")
    if doctor:
        if (root / "package.json").exists():
            missing = not (root / "node_modules").is_dir() and not (root / ".pnp.cjs").is_file()
        else:
            missing = any(not (root / p).exists() for p in dev["dependencies"]["artifacts"])
        if missing:
            raise ValueError("Dependencies missing; run ./scripts/setup")
        result = subprocess.run(["git", "config", "--get", "core.hooksPath"], cwd=root, capture_output=True, text=True)
        if result.stdout.strip() != ".githooks":
            raise ValueError("Hooks missing; run ./scripts/setup")
    else:
        run(["mise", "exec", "--", *install], root)
        run(["git", "config", "core.hooksPath", ".githooks"], root)
        for command in dev["localCommands"]:
            run(["mise", "exec", "--", *command], root)

    import halo
    halo.prepare(root, doctor)
    if doctor:
        print("Local configuration, tools, dependency presence and hooks verified; no provisioning performed.")
        print("Cloud credentials and dependency freshness are not certified by doctor.")
    else:
        print("Checkout ready. Start development separately; see docs/agents/repository.md.")
