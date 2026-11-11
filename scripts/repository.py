#!/usr/bin/env python3
"""Render, validate and audit the canonical repository standard."""
import argparse
import hashlib
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from urllib.parse import quote, urlsplit

from development import read_config

ROOT = Path(__file__).resolve().parent.parent
TEMPLATE = "sshickles/repo-standard"
RULESET_NAME = "Repo standard: default branch"


def run(args, *, cwd=None, data=None, missing_ok=False):
    result = subprocess.run(args, cwd=cwd, input=data, text=True, capture_output=True,
                            env={**os.environ, "GH_HOST": "github.com"})
    if result.returncode:
        if missing_ok:
            try:
                response = json.loads(result.stdout)
            except json.JSONDecodeError:
                response = None
            if isinstance(response, dict) and str(response.get('status')) == '404':
                return 'null'
        if args[:3] == ["gh", "auth", "status"]:
            raise RuntimeError("GitHub credentials missing or invalid; run gh auth login and verify account/SSO access")
        if args[:3] == ["coderabbit", "auth", "status"]:
            raise RuntimeError("CodeRabbit authentication failed; use independent review without browser login")
        raise RuntimeError(f"{Path(args[0]).name} operation failed (exit {result.returncode}); check permissions, plan and connectivity locally. Output withheld to protect secrets")
    return result.stdout.strip()


def api(endpoint, method="GET", payload=None, *, missing_ok=False):
    args = ["gh", "api", "--method", method, endpoint]
    if payload is not None:
        args += ["--input", "-"]
    output = run(args, data=json.dumps(payload) if payload is not None else None, missing_ok=missing_ok)
    return json.loads(output) if output else None


def repository(value):
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9-]*/[A-Za-z0-9][A-Za-z0-9_.-]*", value):
        raise argparse.ArgumentTypeError("Use an explicit GitHub OWNER/REPOSITORY")
    return value


def desired_rules(policy=None):
    from standard import rules
    config = policy or read_config(ROOT / '.repo-standard.json')
    return rules(config, {'ruleset.json': (ROOT / 'ruleset.json').read_text()})


def rules_match(actual, desired):
    # GitHub adds read-only metadata and may add false-valued defaults.
    # All configured values must match, with no extra rules or bypass actors.
    def matches(have, want):
        if isinstance(want, dict):
            return isinstance(have, dict) and all(k in have and matches(have[k], v) for k, v in want.items())
        if isinstance(want, list):
            return isinstance(have, list) and len(have) == len(want) and all(
                any(matches(item, expected) for item in have) for expected in want
            )
        return have == want
    return matches(actual, desired)


def list_rules(repo):
    pages = json.loads(run(["gh", "api", "--paginate", "--slurp", f"repos/{repo}/rulesets?includes_parents=true&per_page=100"]))
    return [item for page in pages for item in page]


def inspect(repo, policy=None):
    info = api(f"repos/{repo}")
    if info.get("archived") or info.get("disabled"):
        raise RuntimeError("The repository is archived or disabled")
    if not info.get("permissions", {}).get("admin"):
        raise RuntimeError(f"Administrator access is required for {repo}")
    if policy and info.get("default_branch") != policy["git"]["baseBranch"]:
        raise RuntimeError("Configured baseBranch differs from GitHub default branch; reconcile explicitly before configuring protections")
    desired = desired_rules(policy)
    rules = list_rules(repo)
    owned = [r for r in rules if r["name"] == RULESET_NAME and r.get("source_type") == "Repository"
             and r.get("source", "").lower() == repo.lower()]
    if len(owned) > 1:
        raise RuntimeError("Multiple rulesets have the standard's name; reconcile them manually")
    current = api(f"repos/{repo}/rulesets/{owned[0]['id']}") if owned else None
    if current and not rules_match(current, desired):
        raise RuntimeError("The standard's ruleset has different settings. Review it manually; nothing was overwritten.")
    other = [r for r in rules if r not in owned]
    legacy = api(f"repos/{repo}/branches/{quote(info['default_branch'], safe='')}/protection", missing_ok=True)
    return info, desired, current, other, legacy


def approval_digest(repo, desired, settings, observed, create_ruleset, other=(), legacy=None):
    # Bind every listed field, including update timestamps, independent of API order.
    others = sorted(other, key=lambda rule: json.dumps(rule, sort_keys=True))
    payload = json.dumps({'repository': repo.lower(), 'ruleset': desired, 'settings': settings,
                         'observed': observed, 'createRuleset': create_ruleset,
                         'otherRulesets': others, 'legacyProtection': legacy}, sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(payload.encode()).hexdigest()


def configure(repo, *, apply=False, backup_dir=None, policy=None, approval_reference=None):
    info, desired, current, other, legacy = inspect(repo, policy)
    print(f"Repository: {repo}")
    checks = next(r for r in desired["rules"] if r["type"] == "required_status_checks")
    print("Required checks: " + ", ".join(c["context"] for c in checks["parameters"]["required_status_checks"]))
    settings = {"allow_auto_merge": True, "allow_squash_merge": True,
                "delete_branch_on_merge": True}
    print("Proposed ruleset:\n" + json.dumps(desired, indent=2))
    print("Proposed repository settings:\n" + json.dumps(settings, indent=2))
    observed = {key: info.get(key) for key in settings}
    print("Observed repository settings:\n" + json.dumps(observed, indent=2))
    print("Ruleset action: " + ("create" if current is None else "already matches"))
    print('Observed additional and inherited rulesets:\n' + json.dumps(other, indent=2))
    print('Observed legacy branch protection:\n' + json.dumps(legacy, indent=2))
    digest = approval_digest(repo, desired, settings, observed, current is None, other, legacy)
    print("Approval digest: sha256:" + digest)
    for rule in other:
        print(f"Preserving additional ruleset: {rule['name']} ({rule.get('source_type')})")
    if not apply:
        print("Preview only. Run with --apply to configure GitHub.")
        return
    if not approval_reference or not re.fullmatch(r'\S+#sha256:' + digest, approval_reference):
        raise RuntimeError("Approval reference must name owner approval and end with #sha256: plus the exact preview digest; obtain owner approval first")
    backup_dir = Path(backup_dir or Path.home() / ".local/state/repo-standard")
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    backup = backup_dir / f"{repo.replace('/', '--')}-{stamp}.json"
    with backup.open("x") as stream:
        os.chmod(backup, 0o600)
        json.dump({"repository": info, "managed_ruleset": current, "other_rulesets": other,
                   'legacy_protection': legacy}, stream, indent=2)
    latest_info, _, latest_current, latest_other, latest_legacy = inspect(repo, policy)
    keys = tuple(settings)
    if (any(latest_info.get(key) != info.get(key) for key in keys)
            or latest_current != current
            or approval_digest(repo, desired, settings, observed, latest_current is None,
                               latest_other, latest_legacy) != digest):
        raise RuntimeError('GitHub configuration changed since preview; review the approval batch again')
    # Add protections before allowing auto-merge. Never delete another ruleset.
    if not current:
        api(f"repos/{repo}/rulesets", "POST", desired)
    api(f"repos/{repo}", "PATCH", settings)
    updated, _, verified, _, _ = inspect(repo, policy)
    if not verified or any(updated.get(k) != v for k, v in settings.items()):
        raise RuntimeError("GitHub did not retain the requested configuration; inspect the repository settings")
    print(f"GitHub configuration verified. Previous settings saved to {backup}")
    print("Integration setup is still required. Follow docs/setup.md and verify one real PR.")


def verify_destination(path, policy):
    """Verify adoption identity using the configured remote, without network access."""
    remote = policy["git"]["remote"]
    urls = run(["git", "remote", "get-url", "--all", remote], cwd=path).splitlines()
    urls += run(["git", "remote", "get-url", "--push", "--all", remote], cwd=path).splitlines()
    if not urls:
        raise RuntimeError("Configured destination remote has no URLs")
    for url in urls:
        if url.startswith("git@github.com:"):
            identity = url.removeprefix("git@github.com:")
        else:
            parsed = urlsplit(url)
            if parsed.hostname != "github.com":
                raise RuntimeError("Adoption requires the configured remote to identify the destination on github.com")
            identity = parsed.path.lstrip("/")
        if identity.removesuffix(".git").lower() != policy["repository"].lower():
            raise RuntimeError("Policy repository differs from a configured destination URL; nothing was changed")



# Generation and offline integrity are shared by the common check command.
from standard import validate, update, snapshot, render, LOCK


def stamp(revision, apply=False):
    """Canonical authoring only: generate the two provenance files from committed HEAD."""
    from standard import git as source_git, target_path
    top = Path(source_git(ROOT, 'rev-parse', '--show-toplevel').decode().strip()).resolve()
    if top != ROOT:
        raise RuntimeError('Stamp must run from the canonical checkout root')
    metadata = target_path(ROOT, '.repo-standard.json')
    config = read_config(metadata)
    if config['repository'] != TEMPLATE:
        raise RuntimeError('Only sshickles/repo-standard can stamp canonical source')
    verify_destination(ROOT, config)
    data = snapshot(ROOT, revision)
    head = source_git(ROOT, 'rev-parse', 'HEAD').decode().strip()
    if data['revision'] != head:
        raise RuntimeError('Stamp requires the committed source HEAD revision')
    inputs = {**data['files'], '.repo-standard.json':
              source_git(ROOT, 'show', head + ':.repo-standard.json').decode()}
    for name, content in inputs.items():
        if target_path(ROOT, name).read_bytes() != content.encode():
            raise RuntimeError('Commit canonical source changes before stamping: ' + name)
    output = render(data, config)
    changed = {}
    for name in (LOCK, 'docs/agents/policy.md'):
        target = target_path(ROOT, name)
        if not target.exists() or target.read_text() != output[name]:
            changed[name] = output[name]
    print('Canonical source: ' + head)
    print('Provenance plan: ' + (', '.join(changed) or 'already current'))
    if apply:
        for name, content in changed.items():
            target = target_path(ROOT, name)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content)
    return changed


def initialization(path, data, policy):
    """Personalize a newly created template copy without retaining canonical app details."""
    from standard import plan
    output = plan(path, data, policy)
    output['docs/agents/repository.md'] = data['files']['policy/repository.md']
    output['README.md'] = (f"# {policy['repository']}\n\n"
                           "Read [AGENTS.md](AGENTS.md) and [setup](docs/setup.md).\n"
                           "Complete repository-specific instructions before finishing the rollout.\n")
    package = path / 'package.json'
    if package.exists():
        content = json.loads(package.read_text())
        content['name'] = policy['repository'].split('/')[1].lower()
        output['package.json'] = json.dumps(content, indent=2) + '\n'
    return output


def new_repo(args):
    destination = Path(args.root).expanduser().resolve() / args.repo
    if destination.exists():
        raise RuntimeError(f"Destination already exists: {destination}; preserve it and use adoption")
    print(f"Create {args.repo} from {args.template_repo}; clone into {destination}.")
    print("No GitHub merge settings will be changed. Configure them only after owner batch approval.")
    data = snapshot(ROOT, args.revision)
    render(data, args.policy)
    if not args.apply:
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    run(["gh", "repo", "create", args.repo, "--template", args.template_repo,
         "--public" if args.public else "--private"])
    try:
        default_branch = api(f'repos/{args.repo}')['default_branch']
        if args.policy['git']['baseBranch'] != default_branch:
            raise RuntimeError('git.baseBranch differs from the created GitHub default branch; reconcile explicitly before initialization')
        run(["gh", "repo", "clone", args.repo, str(destination), "--", "--origin", args.policy['git']['remote']])
        run(["git", "switch", "-c", "chore/canonical-standard"], cwd=destination)
        # Template copies carry another identity. Initialization is an explicit
        # new-repository operation, separate from conflict-preserving adoption.
        from standard import EXECUTABLES, target_path
        for name, content in initialization(destination, data, args.policy).items():
            target = target_path(destination, name)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content)
            if name in EXECUTABLES:
                target.chmod(0o755)
    except Exception:
        print(f"Repository retained: {args.repo}; checkout: {destination}. See docs/setup.md.", file=sys.stderr)
        raise
    print("Initialization is local and uncommitted. Run setup, checks and review before the rollout PR.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ('adopt', 'update', 'audit'):
        cmd = sub.add_parser(name, help='Report a local rollout diff; explicit --apply requires a clean task checkout')
        if name == 'audit':
            cmd.description = 'Report only: update available exits 0; drift or invalid structure exits nonzero.'
        cmd.add_argument('path', type=Path)
        cmd.add_argument('--source', type=Path, default=ROOT)
        cmd.add_argument('--revision', required=True)
        cmd.add_argument('--config', type=Path)
        if name != 'audit':
            cmd.add_argument('--apply', action='store_true')
    author = sub.add_parser('stamp', help='Canonical checkout only: preview provenance from committed HEAD')
    author.add_argument('--revision', required=True)
    author.add_argument('--apply', action='store_true')
    check = sub.add_parser('validate', help='Validate offline policy provenance and required structure')
    check.add_argument('path', type=Path, nargs='?', default=ROOT)
    config = sub.add_parser('configure', help='Preview GitHub settings; applying requires separate owner batch approval')
    config.add_argument('repo', type=repository)
    config.add_argument('--config', type=Path, required=True)
    config.add_argument('--apply', action='store_true')
    config.add_argument('--approval-reference', help='Exact owner-approved settings batch reference')
    new = sub.add_parser('new')
    new.add_argument('repo', type=repository)
    new.add_argument('--config', type=Path, required=True)
    new.add_argument('--revision', required=True)
    new.add_argument('--template-repo', type=repository, default=TEMPLATE)
    new.add_argument('--root', default='/src')
    new.add_argument('--public', action='store_true')
    new.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    try:
        if args.command == 'validate':
            validate(args.path)
            return 0
        if args.command == 'stamp':
            stamp(args.revision, args.apply)
            return 0
        args.policy = read_config(args.config or args.path / '.repo-standard.json')
        if args.command in ('new', 'configure') and args.repo != args.policy['repository']:
            raise RuntimeError('--config repository must match the destination')
        if args.command == 'new':
            new_repo(args)
        elif args.command == 'configure':
            if args.apply and not args.approval_reference:
                raise RuntimeError('Live settings require --approval-reference to the exact owner-approved batch')
            configure(args.repo, apply=args.apply, policy=args.policy, approval_reference=args.approval_reference)
        else:
            if args.command == 'adopt':
                verify_destination(args.path, args.policy)
            if args.command in ('audit', 'update') and not (args.path / LOCK).is_file():
                raise RuntimeError('Canonical lock missing: adopt the standard explicitly before auditing or updating')
            if args.command == 'update' and args.apply:
                verify_destination(args.path, args.policy)
            # New revisions are informational; validation drift raises a failure.
            update(args.path, args.source, args.revision, args.policy, getattr(args, 'apply', False),
                   strict=args.command == 'audit')
    except (RuntimeError, OSError, ValueError, KeyError, TypeError, subprocess.CalledProcessError) as error:
        print(f'Error: {error}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
