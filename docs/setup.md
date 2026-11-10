# Repository setup and updates

## Prerequisites and configuration

Use Git, Python 3.11+ and mise on the assigned Linux development host. Linux is
the only supported development platform. GitHub operations also need
GitHub CLI with access to the destination. Trust reviewed mise configuration
with `mise trust` if prompted. The pinned tools and locked installs are selected
by this checkout, not by global package versions. No service credentials are
needed for the starter. Setup never deploys or administers host services.

Copy `.repo-standard.json` and review the destination identity, actual default
branch and remote, stack profile, `ciChecks` (exact ordinary PR check contexts
and known integration IDs), finite `validation` argv lists, the stack `testCommand`, integrations and
branch/issue conventions. `integrations.deploymentCheck` is informational.
Greptile is required for rollout completion. There is no auto-merge permission
gate in configuration. Do not put tokens, secret arguments or cloud IDs from
another project in public configuration.

`mise.toml` pins tools. Node stacks also pin `packageManager` with its matching
lockfile. Setup supports pnpm frozen installs, npm ci and Yarn 2+ immutable
installs. Custom non-Node stacks declare `development.dependencies` with a
committed `lockfile`, a locked `install` argv list and generated `artifacts`.
Review those stack-specific commands before use. `development.requiredFiles`
lists ignored files pulled from the service's authoritative store. Setup refuses
missing artifacts before dependent commands. Reviewed, finite `localCommands`
may generate local outputs; they must not deploy as a setup side effect.
Production is not a separate setup approval gate: finite pulls and local
generation may use a reviewed production mapping. All initializers must remain
idempotent and non-deploying, regardless of environment. The command-token
filter catches obvious deployments; it cannot prove arbitrary scripts safe.
Review each adapter and validate its actual destination before executing it.
Document actual service/environment mappings in repository instructions. An
environment label alone does not verify a cloud destination.

## Migrate older configuration

Version 1 is not upgraded by changing only its version number. Build a version 2
input from the current `.repo-standard.json` on an adoption branch, preserving
the application's package manager, lockfile and actual conventions. The old
`--template nextjs` and `--deployment-check` flags became `profile` and
`integrations.deploymentCheck`. The latter is now informational.

Earlier version 2 inputs also need explicit `ciChecks` and `testCommand`.
Remove `review.allowAutoMerge`; keep `review.coderabbit`, and select the required
Greptile integration. Review `git.remote`, `git.baseBranch`, `validation`,
`development` and `conventions` against the destination. Do not infer missing
integrations or approvals. Preview adoption and resolve workflow and hook
conflicts before applying; preserve unrelated application files and settings.

## New repository bootstrap

From a reviewed canonical checkout, resolve an immutable source revision with
`git rev-parse HEAD`. Preview creation, then explicitly create when authorized:

```sh
./scripts/new-repo OWNER/REPO --config /tmp/repository.json --revision SOURCE_SHA
./scripts/new-repo OWNER/REPO --config /tmp/repository.json --revision SOURCE_SHA --apply
```

Creation defaults to a private GitHub template copy and `/src/OWNER/REPO`;
`--public`, `--root` and `--template-repo` are explicit alternatives. It leaves
local personalization on `chore/canonical-standard`. It does not push, create a
PR, change live merge settings or provision a cloud service. The published
GitHub template and selected canonical revision should agree. Initialization replaces the canonical repository details with the seven-section
template and personalizes README and package name. Fill in application details
and verify the actual GitHub default branch before continuing.

Run `./scripts/setup`, `./scripts/setup --doctor`, `./scripts/check` and
`./scripts/review` in the new checkout. Complete repository-specific instructions
and integration setup, then use one rollout PR and native squash auto-merge.
Missing live settings or review integration are pending dependencies, not gates
to bypass. Verify that server-side protections enforce required checks and
current-head Greptile 5/5 approval before enabling auto-merge. Leave the PR open
with auto-merge off if those gates are not yet enforced. The optional T3 adapter is documented in
[t3-compatibility.md](t3-compatibility.md). A saved creation action must be imported
and updated explicitly; committing `t3.json` does not activate saved actions.

## Adopt an existing repository

Use its task worktree, starting from the latest remote default branch. Run the
generator from a reviewed canonical checkout, targeting only that worktree:

```sh
python3 scripts/repository.py adopt /path/to/task --config /tmp/repository.json --revision SOURCE_SHA
python3 scripts/repository.py adopt /path/to/task --config /tmp/repository.json --revision SOURCE_SHA --apply
```

The default is a report with unified diffs. Apply requires a clean checkout,
verifies the destination's configured fetch and push URLs and refuses conflicts
before writing. It preserves repository.md, unrelated workflows, unrelated permission settings
and other files.
Existing workflow, hook, permission or instruction conflicts require explicit
manual integration on the task branch. Do not replace an application's CI or
hook manager blindly. Keep stack setup underneath the four command interfaces,
run check in its real CI job and preserve other responsibilities. For a custom
stack, adjust validation, test command and pinned tooling deliberately before
finishing adoption. The test entry point runs the pinned `testCommand`; set it to the
destination suite. Check always runs test in addition to configured validation.

### Preserve repository pre-push checks

Keep the generated `.githooks/pre-push` and `scripts/pre_push.py` unchanged.
Move existing repository-specific pre-push responsibilities into executable files
under `.githooks/pre-push.d/`, for example `10-existing-check`. Commit these files
with the executable bit set. Setup still refuses a different hook manager until
you integrate its responsibilities and explicitly select `.githooks`.

The shared hook first rejects every default-branch destination, including
deletions, then runs `./scripts/check`. After that succeeds, it runs every entry
in `.githooks/pre-push.d/` in filename order from the checkout root. Each entry
receives the original remote name and URL as arguments and its own complete,
unchanged copy of the pushed ref lines on stdin. This includes branch deletions
and pushes containing multiple refs. Any nonzero exit blocks the push and stops
the chain. An absent or empty directory adds no checks. All entries must be
regular executable files; directories, symlinks and non-executable files fail
both validation and the hook. Do not put README files or placeholders there.
Canonical updates preserve these repository-owned files.

The repository.md template starts with no exceptions. Fill its seven sections
with real architecture, commands, ownership, runtime, verification and recovery
information. Remove superseded entry points and duplicate policy prose after
migrating callers. Thin instruction adapters point to AGENTS.md.

## Integrity and canonical updates

`policy/policy.md` is the canonical body. `.repo-standard-source.json` embeds
canonical files and Git commit/tree/blob proofs anchored to its recorded source
commit SHA. The generated header records that SHA and the body's SHA-256 digest.
Offline validation derives the expected body from verified Git objects. Editing
the generated body, checksum or embedded source alone fails. The recorded SHA
is the trust anchor: review changes to it as source upgrades, just as dependency
lock updates. This detects drift; it does not defend against replacing the
validator and trust anchor together.

Run these commands from a separate, reviewed canonical checkout at `NEW_SHA`,
not through the target repository's installed generator. `--source` selects input
files; it does not upgrade the running generator or its fixed file manifest.
Older installed generators omit newly introduced helpers and generated outputs,
which can leave checks and subsequent local updates unable to start. The current
canonical generator is the supported bootstrap for upgrades, including recovery
from a partial installed-generator update. Preserve and commit any partial update
on the task branch first; keep the existing lock for integrity and collision checks.
If an interrupted update changed checked commands before refreshing the lock,
validation, audit and update reject that drift. Preserve the partial changes in a
commit, restore the checked commands to their last valid installed versions
matching the retained lock, commit that restoration, and retry from the selected
canonical checkout.

```sh
cd /path/to/canonical
python3 scripts/repository.py validate /path/to/task
python3 scripts/repository.py audit /path/to/task --source /path/to/canonical --revision NEW_SHA
python3 scripts/repository.py update /path/to/task --source /path/to/canonical --revision NEW_SHA
python3 scripts/repository.py update /path/to/task --source /path/to/canonical --revision NEW_SHA --apply
```

Audit and update preview return success with "update available" for an internally
consistent older revision. They never fetch, reset or rewrite the target. Fetch
the canonical source separately. Apply requires a clean task checkout, refuses
local changes conflicting with prior generated files and differing existing
application files at paths the new revision first manages. Integrate these
collisions manually on the task branch before retrying.
Local integrations are preserved when the canonical file is unchanged between
the recorded and selected revisions. Shared commands and the hook still require
exact content from the recorded revision. The caller selects the
reviewed canonical revision; ancestry is not required because native squash
merging can replace the original source history. It is safe to rerun. Finish, check and review the diff,
then update the repository's existing `chore/canonical-standard` rollout PR
rather than creating another. Do not rebase or force-push a published branch.
No command automatically opens PRs or changes live settings.

For this canonical repository, commit source changes first, then preview and
apply provenance with the canonical-only authoring command:

```sh
python3 scripts/repository.py stamp --revision HEAD
python3 scripts/repository.py stamp --revision HEAD --apply
./scripts/check
```

Stamp verifies canonical identity, remote URLs, checkout root and exact committed
source inputs. It writes only the two generated provenance files. It refuses
uncommitted source inputs, preserves unrelated files and is safe to rerun.
Commit the generated output after checks and review. Downstream repositories
continue using update, which rejects drift from their recorded revision. The generated
revision identifies the actual source commit without a self-referential SHA.
The two commits travel in one rollout PR. An audit may report a newer commit
containing identical policy; it is informational until an explicit update.

The weekly and canonical-file-change `policy-audit.yml` workflows produce a
summary and artifact with the planned diff. A green audit means the recorded revision is internally consistent,
not that it is current. Update availability is informational; policy drift fails.
They are report-only, with no live
settings or PR writes. `GITHUB_TOKEN` suffices to read this repository and a
public canonical source. If the canonical repository is private, Steve must add
`REPO_STANDARD_READ_TOKEN` with read-only contents access to it in each audited
repository. A token is not needed merely to run offline validation. Automated
cross-repository PR publishing is not enabled; a future publisher must discover
and update the existing rollout PR, use authorized write credentials and honor
review and merge gates.

## Live settings and reviewer setup

File rendering does not change live GitHub settings. Before any live changes,
inspect repository and inherited rulesets and legacy protection, actual recent
PR check names, integration bindings and current bypass actors. Present one
exact owner approval batch, including removal of deployment requirements.
Preserve unrelated protections and bypass actors. The `configure` preview
refuses conflicting managed rulesets rather than overwriting them. Reconcile
existing protections in the approved plan; never add a redundant ruleset to
work around a conflict. A ruleset with changed bypass actors requires explicit
review. This task does not apply that plan.

`apply-ruleset.sh OWNER/REPO --config FILE` only previews.
Explicit writes additionally require `--apply --approval-reference REFERENCE`
using `REFERENCE#sha256:DIGEST`, with the exact digest printed by preview.
The digest binds the reference to the target repository, proposed payload,
observed settings and whether a ruleset will be created. A changed observed
state between preview and apply invalidates the reference. The preview also
shows additional and inherited ruleset records and legacy default-branch
protection; both are bound to the digest and checked again before writes. A
legacy-protection 404 is recorded as absent; other read errors block the operation.
It does not establish
owner approval; obtain approval for that exact batch before applying. Re-read settings immediately before approved writes and verify
afterwards. Dashboard setup remains a separate owner step.

Greptile fields follow the
[greptile.json reference](https://www.greptile.com/docs/code-review/greptile-json-reference)
and its [auto-approve schema](https://www.greptile.com/docs/code-review/greptile-config-reference#auto-approve).
Repository scope belongs under `autoApprove.filters.includeRepositories`.
Separately verify dashboard confidence required to pass is 5 and repository
scoped auto-approval is enabled. Do not infer either from the file. Reference
PR #2257 in `prison-professors/website` merged at
`773865a51a30a0aa3b8d46ec91e2a42015e4a12f`; its instructions and reviewer files
were inspected as a reference, with the approved shared policy taking precedence.

Claude Code adapter rules follow its
[permission syntax](https://code.claude.com/docs/en/permissions).
Deny takes precedence over allow. `:*` is a trailing prefix wildcard, while
`*` inside a Bash pattern spans arguments. The two merge allows are specific
to native squash auto-merge and disabling it. Admin denials match added admin
flags even on an otherwise allowed command. There is no blanket merge denial.
These patterns are adapter guidance, not a general shell security boundary;
wrappers and alternate executable paths have documented limitations. The real
hook checks destination refs and GitHub enforces protections.
The merge allow patterns cover command forms, including authorized explicit
repository arguments. They do not authorize changes to other repositories.
Verify each target against the owner's assigned scope before a GitHub write.

## Recovery

Creation refuses an existing destination. After partial failure, retain the
created repository and local checkout, inspect the error, and resume adoption
or setup instead of rerunning creation or deleting work. Setup refuses an
unrelated hook manager and reports missing prerequisites without secret output.
Review uses configured local profiles without probing credentials; unavailable
or failed review directs the independent fallback and exits nonzero.

For worktree cleanup, check active users and processes, ignored/untracked files,
unpublished commits and the final PR head. Preserve uncertain data and remove
through the owning manager without force. Never reset or clean another task to
make adoption or an update pass.
