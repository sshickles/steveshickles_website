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
    mapping = dev.get("changedTestCommand")
    if mapping is not None:
        if (not isinstance(mapping, dict) or set(mapping) != {"kind", "command"}
                or mapping["kind"] not in ("vitest", "pytest", "unittest")):
            raise ValueError("development.changedTestCommand requires kind (vitest, pytest or unittest) and command")
    if mapping is not None and mapping["kind"] == "vitest":
        runner = mapping["command"]
        if (not isinstance(runner, list) or not runner or runner[-1] != "vitest"
                or config["testCommand"][:len(runner) + 1] != [*runner, "run"]):
            raise ValueError("Vitest mapping command must end in vitest and testCommand must start with that command plus run")
    if (mapping is not None and mapping["kind"] == "pytest"
            and mapping["command"] != config["testCommand"]):
        raise ValueError("Pytest mapping command must equal testCommand, including all suite options")
    if mapping is not None and mapping["kind"] == "unittest":
        runner = mapping["command"]
        if (not isinstance(runner, list) or len(runner) < 3 or runner[-2:] != ["-m", "unittest"]
                or config["testCommand"][:len(runner) + 1] != [*runner, "discover"]):
            raise ValueError("Unittest mapping must end in -m unittest and testCommand must start with that command plus discover")
    globs = dev.get("sharedInfrastructureGlobs", [])
    if not isinstance(globs, list) or any(
        not isinstance(g, str) or not g or Path(g).is_absolute() or ".." in Path(g).parts
        for g in globs
    ):
        raise ValueError("development.sharedInfrastructureGlobs must contain checkout-relative globs")
    if "sharedInfrastructureGlobs" in dev:
        dev["sharedInfrastructureGlobs"] = [g.removeprefix("./") for g in globs]
    commands = config["validation"] + dev["localCommands"] + [config.get("testCommand")]
    if mapping is not None:
        commands = commands + [mapping["command"]]
    if "dependencies" in dev:
        if not isinstance(dev["dependencies"], dict):
            raise ValueError("development.dependencies must be an object")
        adapter = dev["dependencies"]
        if adapter.get("mode") == "none":
            if set(adapter) != {"mode"}:
                raise ValueError("No-dependencies mode accepts only mode: none")
        else:
            if adapter.get("mode", "locked") != "locked":
                raise ValueError("dependencies.mode must be locked or none")
            commands = commands + [adapter.get("install")]
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
    declared_tools = dev.get("tools", {})
    if not isinstance(declared_tools, dict) or any(
        not isinstance(k, str) or not k or not isinstance(v, str)
        or not re.fullmatch(r"\d+\.\d+\.\d+", v) for k, v in declared_tools.items()
    ):
        raise ValueError("development.tools must map tool names to exact x.y.z pins")
    ci = config.get("existingCI")
    if ci is not None:
        if (not isinstance(ci, dict) or set(ci) != {"workflow", "job", "context"}
                or not all(isinstance(v, str) and v for v in ci.values())
                or not re.fullmatch(r"\.github/workflows/[A-Za-z0-9_.-]+\.ya?ml", ci["workflow"])
                or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_-]*", ci["job"])
                or ci["context"] not in [c["context"] for c in checks]):
            raise ValueError("existingCI requires workflow, job and a context listed in ciChecks")
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
    if not (root / "mise.toml").is_file():
        raise ValueError("Missing mise.toml; adopt the repository tool configuration before setup")
    tools = tomllib.loads((root / "mise.toml").read_text()).get("tools", {})
    if not isinstance(tools, dict) or any(not isinstance(v, str) or not re.fullmatch(r"\d+\.\d+\.\d+", v) for v in tools.values()):
        raise ValueError("Pin every mise.toml tool to an exact x.y.z version")
    config = config or read_config(root / ".repo-standard.json")
    if config["development"].get("dependencies", {}).get("mode") == "none":
        package_file = root / "package.json"
        if package_file.exists():
            package_data = json.loads(package_file.read_text())
            if not isinstance(package_data, dict):
                raise ValueError("package.json must contain an object")
            fields = ("dependencies", "devDependencies", "optionalDependencies")
            if any(not isinstance(package_data.get(key, {}), dict) for key in fields):
                raise ValueError("Package dependency fields must be objects")
            if any(package_data.get(key) for key in fields):
                raise ValueError("No-dependencies mode conflicts with declared package dependencies")
        return tools, []
    if not tools:
        raise ValueError("Locked dependency installs require exact mise tool pins")
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
        if not install:
            missing = False
        elif (root / "package.json").exists():
            missing = not (root / "node_modules").is_dir() and not (root / ".pnp.cjs").is_file()
        else:
            missing = any(not (root / p).exists() for p in dev["dependencies"]["artifacts"])
        if missing:
            raise ValueError("Dependencies missing; run ./scripts/setup")
        result = subprocess.run(["git", "config", "--get", "core.hooksPath"], cwd=root, capture_output=True, text=True)
        if result.stdout.strip() != ".githooks":
            raise ValueError("Hooks missing; run ./scripts/setup")
    else:
        if install:
            run(["mise", "exec", "--", *install], root)
        run(["git", "config", "core.hooksPath", ".githooks"], root)
        for command in dev["localCommands"]:
            run(["mise", "exec", "--", *command], root)

    if doctor:
        from pre_push import repository_checks
        for check in repository_checks(root, '.githooks/doctor.d'):
            run([str(check)], root)
    import halo
    halo.prepare(root, doctor)
    if doctor:
        print("Local configuration, tools, dependency presence and hooks verified; no provisioning performed.")
        print("Cloud credentials and dependency freshness are not certified by doctor.")
    else:
        print("Checkout ready. Start development separately; see docs/agents/repository.md.")
