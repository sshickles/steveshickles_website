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
For repositories with no dependencies, set `development.dependencies` to
`{"mode": "none"}`. Setup and doctor then need no package manifest, lockfile or
dependency artifacts. Declared Node package dependencies conflict with this mode.
For custom adoption without an existing `mise.toml`, declare exact tool versions in
`development.tools`, for example `{"python": "3.13.5"}`. The generated file contains
only those tools; an empty object produces an empty tools table. Existing mise
files are preserved; `development.tools` is an initial rendering input, not a
second source of pins. Even no-dependencies mode requires `mise.toml` (an empty
`[tools]` table is valid). The exact mise pin is the source of truth, not a floating
CI version such as `node-version: "24"`. Canonical CI installs mise and calls
`./scripts/setup --ci`, which installs the pinned tools, locked dependencies and
hooks before `./scripts/check`. This explicit bootstrap mode skips local service
attachment, local artifact requirements, `localCommands` and host runtime setup.
It needs no Vercel or Convex login or project link. It does not create `.env.local`.
CI still runs the full check without arguments and supplies any build or test
inputs through its own configuration. Use `--ci` in preserved CI workflows too.
Normal setup never infers this mode from the `CI` environment variable; it retains
the required service attachment. `--ci` and `--doctor` are mutually exclusive.
Review those stack-specific commands before use. `development.requiredFiles`
lists ignored files pulled from the service's authoritative store. Local setup refuses
missing artifacts before dependent commands. Reviewed, finite `localCommands`
may generate local outputs; they must not deploy as a setup side effect.
Production is not a separate setup approval gate: finite pulls and local
generation may use a reviewed production mapping. All initializers must remain
idempotent and non-deploying, regardless of environment. The command-token
filter catches obvious deployments; it cannot prove arbitrary scripts safe.
Review each adapter and validate its actual destination before executing it.
Document actual service/environment mappings in repository instructions. An
environment label alone does not verify a cloud destination.

## Shared Convex and Vercel setup

Every checkout with `convex/` must declare a shared cloud development deployment.
Missing `development.convex` is configuration drift in both audit and validation.
Use the same template adapter in every repository, removing redundant service
scripts from `localCommands` and owned doctor hooks during rollout:

```json
{
  "development": {
    "environment": "development",
    "requiredFiles": [".env.local"],
    "localCommands": [],
    "vercel": {
      "environment": "development",
      "projectId": "prj_example",
      "orgId": "team_example",
      "requiredKeys": ["NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY"]
    },
    "convex": {
      "deployment": "dev:benevolent-dolphin-855",
      "urlVariable": "NEXT_PUBLIC_CONVEX_URL",
      "additionalDeployments": {
        "secondary": {
          "deployment": "dev:shared-secondary-123",
          "deployKeyVariable": "CONVEX_SECONDARY_DEPLOY_KEY"
        }
      }
    }
  }
}
```

Keep the required affected-test mapping and other development fields alongside
these fields. `vercel` requires `environment: development` and the expected
`projectId`. Optional `orgId` pins the organization or team too. Audit rejects
every `development.vercel` object missing its expected project ID, including
repositories without Convex. Optional `requiredKeys` lists environment variable
names that must be present and nonempty in the merged `.env.local` after a pull
and during doctor. Missing or empty keys fail without printing values. `convex`
requires an explicit `dev:<name>` selector, never `prod`, `local` or a personal
project selector. It also accepts optional `url` and `urlVariable` fields.
When present, `urlVariable` names the frontend's
Convex URL variable, such as `NEXT_PUBLIC_CONVEX_URL`, `VITE_CONVEX_URL` or
`CONVEX_URL`. Its value defaults to `https://<name>.convex.cloud`. For a regional deployment,
set optional `convex.url`, for example
`"https://shared-fixture-123.eu-west-1.convex.cloud"`. The HTTPS cloud hostname
must start with the configured deployment name; verification compares the full
URL. [Convex documents regional deployment URLs](https://docs.convex.dev/management-api/list-deployments).

Setup requires an existing Vercel login and `.vercel/project.json` link with
project and organization IDs. Setup and doctor compare the link against the
configured project ID and optional organization ID before invoking Vercel.
A mismatch fails with an instruction to correct the link separately; setup
never relinks it. It runs `vercel whoami` before pulling. If login
or link is missing, it fails with an instruction to complete that step separately.
It never logs in, links, creates a project or prompts. Pin Vercel in `mise.toml`
and keep Convex in the locked dependencies. The adapter uses the installed
`node_modules/.bin/convex`, never a downloader that might fetch a different CLI.

After locked dependency installation, setup runs the linked project's
`vercel env pull <temporary-file> --environment development --yes`. It captures
all output, rejects sensitive placeholders, and merges the pulled assignments
into `.env.local`, preserving local-only keys and unrelated text. It overrides
only `CONVEX_DEPLOYMENT` and the configured URL variable with the explicit shared
attachment. Vercel remains the source for the other pulled values; backend
secrets remain in Convex. The generated artifact is never hand-maintained.

The write is atomic with mode 0600. Every normal run tightens an existing
`.env.local` to 0600 even when content is unchanged. Doctor rejects any other
mode without repairing it. Symlinked `.env.local` files are rejected.
Duplicate managed assignments are removed. Identical reruns do not rewrite the
file. Temporary files are removed on success or failure. Before pulling, setup
rejects tracked `.env.local` files and installs uniform local Git excludes for
`/.env.local` and `/.repo-standard-env-*/`. It verifies that both the final artifact
and staging are ignored, including when the repository has no env ignore rules.
Doctor verifies protection without modifying it. The final artifact and interrupted
staging stay out of commits and review input. Staging stays on the checkout
filesystem so replacement is atomic across worktree layouts. An empty Vercel-only
pull still creates an empty, ignored `.env.local` file. Setup rejects conflicting
inherited selectors, deploy keys, deployment tokens and self-hosted credentials;
it does not print or delete them. Correct their authoritative store or shell.

After writing, the installed CLI runs only
`convex function-spec --env-file .env.local`. This read-only query reports its
actual deployment URL; setup compares it with the configured shared deployment
and fails on mismatch or inaccessible login. It never runs `convex dev`,
`convex deploy`, `convex dev --configure`, codegen, function pushes or deployment
creation. `./scripts/setup --doctor` checks the existing attachment and queries
its identity without pulling or writing files. Tests stub both service CLIs and
never contact real deployments. See [Vercel env](https://vercel.com/docs/cli/env)
and [Convex function-spec](https://docs.convex.dev/cli/reference/function-spec).

The adapter selects the primary `convex/` backend. Optional
`development.convex.additionalDeployments` maps backend names to objects with
`deployment: "dev:<name>"` and `deployKeyVariable`. Variable names must be unique
and must not conflict with primary selectors or credentials. Each configured
key is required in the merged `.env.local`. Setup and doctor also inspect it
when present in `.env` or the shell. They require the structural prefix
`dev:<configured-name>|` and a nonempty credential, rejecting production,
preview and other deployment keys without printing values. This does not
authenticate the key or query secondary deployments. Additional keys are
preserved, never replaced with the primary backend's selector. Declare every
additional backend credential during rollout.

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
with auto-merge off if those gates are not yet enforced. A repository with no
required status checks can merge on approval alone once auto-merge is enabled.
Its adoption PR relies on Greptile approval until required contexts are configured;
preview recommends `checks` and `Greptile Review` (integration 867647). Keep both
explicit in `ciChecks`; validation rejects incorrect bindings or drift from the
rendered ruleset. This list owns the required status contexts and their integration
bindings. Preview shows removal of unlisted contexts; add any live CI contexts
that must remain to `ciChecks` before approving the proposal. Existing ruleset
differences require manual reconciliation, and `--apply` refuses them.
The optional T3 adapter is documented in
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
before writing. It preserves repository.md, unrelated workflows and application
files. Canonical AGENTS.md and settings replace local variants. Existing workflow
and hook conflicts require explicit manual integration on the task branch. Do not replace an application's CI or
hook manager blindly. Keep stack setup underneath the four command interfaces,
run check in its real CI job and preserve other responsibilities. For a custom
stack, adjust validation, test command and pinned tooling deliberately before
finishing adoption. The test entry point runs the pinned `testCommand`; set it to the
destination suite. Check without arguments always runs test in addition to configured validation.

### Preserve an existing CI job

Set `existingCI` to `{"workflow": ".github/workflows/build.yml", "job": "verify", "context": "checks"}`
and retain `checks` in `ciChecks`. Adoption omits the canonical CI workflow and
preserves the selected file. Validation requires the selected job to have that
name (or job ID if unnamed) and a standalone `- run: ./scripts/check` step.
Use conventional block YAML with two-space job and step indentation as in the
canonical workflow. Dynamic names, aliases and reusable jobs require manual
integration. Keep setup and pinned tools in the existing job. This check verifies
the command contract, not GitHub trigger coverage or successful execution.

### Preserve repository pre-push checks

Keep the generated `.githooks/pre-push` and `scripts/pre_push.py` unchanged.
Move existing repository-specific pre-push responsibilities into executable files
under `.githooks/pre-push.d/`, for example `10-existing-check`. Commit these files
with the executable bit set. Setup still refuses a different hook manager until
you integrate its responsibilities and explicitly select `.githooks`.

The shared hook first rejects every default-branch destination, including
deletions, then runs `./scripts/check --pre-push` with the pushed commit IDs.
After that succeeds, it runs every entry
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

### Configure affected tests for pre-push

CI keeps calling `./scripts/check` without arguments. It runs the complete
`testCommand` and every `validation` command. The required `checks` status stays
the merge gate. `./scripts/test` also keeps running the complete suite.

Hook mode runs integrity validation and all configured `validation` commands,
then selects affected tests. Keep lint, type checking, build and other non-test
checks in `validation`. A command identical to `testCommand` is omitted only in
hook mode to avoid running the suite twice. Split combined wrappers such as
`lint && test` into separate commands when adopting affected tests.

Every repository must set the `development.changedTestCommand` object in `.repo-standard.json`:

```json
{
  "kind": "vitest",
  "command": ["pnpm", "exec", "vitest"]
}
```

All kinds accept an optional `preflight` argv list. Hook mode runs it once,
before selection, on mapped, skipped and full fallback paths. A nonzero exit
fails the push without running tests. It runs through mise from the checkout
root, just like the test command. Full checks and CI retain `testCommand` and
`validation`; keep any checks they need there too. For a test wrapper that checks
tool versions before running Vitest, keep that wrapper as `testCommand` and
expose its version-only check as preflight:

```json
{
  "kind": "vitest",
  "command": ["pnpm", "exec", "vitest"],
  "preflight": ["python3", "scripts/check-tool-versions.py"]
}
```

The version-check script is repository-owned, not supplied by the template.
For Vitest, `command` is a direct runner ending in `vitest`. Normally `testCommand`
starts with that runner plus `run`, for example `["pnpm", "exec", "vitest", "run"]`.
A wrapper `testCommand`, such as `["pnpm", "test"]`, requires preflight so its
prerequisite checks also run before related selection. Its fallback command is
preserved verbatim; related runs use the mapping's direct runner with no wrapper
options. Ensure the direct runner covers the same suite and configuration.
Selection invokes `vitest related <files> --run --passWithNoTests`.
Positional suite filters such as `tests/unit` retain the full command. Options
with separate values also fall back because their values cannot safely be
distinguished from suite filters. Use `--option=value`, such as `--project=unit`,
when enabling related selection with options. It passes only
existing changed JavaScript and TypeScript source or test files. Related runs
disable coverage collection so global coverage thresholds cannot reject a partial
suite. Full checks and full-suite fallbacks keep coverage enforcement. No relevant
files means no tests when the changes contain only conventional documentation.
Unknown inputs such as JSON fixtures, runtime assets and templates trigger the
full suite in unit-test mappings. Documentation-only paths are root `README*`,
`CHANGELOG*`, `LICENSE*`, `COPYING*`, `AUTHORS*`, `CONTRIBUTING*`, and `docs/**`.
Add any documentation consumed at runtime to `sharedInfrastructureGlobs`, which
takes precedence over this skip list. Deleted source or test files trigger the full suite.

Vitest related selection follows static imports. Before enabling the mapping,
add source paths loaded through computed imports such as `import(filepath)`,
filesystem reads, or other dependencies outside Vitest's graph to
`sharedInfrastructureGlobs`. For example, `["src/plugins/**", "fixtures/**"]`
forces full tests when those inputs change. The template cannot infer these
application-specific paths. CI remains the complete-suite gate.

For unittest, use `{"kind":"unittest","command":["python3","-B","-m","unittest"]}`.
The mapping command must end in `-m unittest`; `testCommand` must start with
that command plus `discover`, for example
`["python3","-B","-m","unittest","discover","-s","tests"]`.
Only changed `test_*.py` or `*_test.py` files select dotted module names.
Discovery's `-s` start directory, `-t` import root and `-p` pattern are respected.
The hook adds the import root to the child process's `PYTHONPATH`. Ambiguous
imports, missing package markers, package or module `load_tests` hooks,
interpreter isolation flags (`-I` or `-E`), unsupported options and
tests outside discovery fall back to the full command. Python source changes,
deletions, shared infrastructure, unclassified inputs and changed test modules
referenced elsewhere also run the full suite.

For pytest, use `{"kind": "pytest", "command": ["python3", "-m", "pytest"]}`.
The mapping's `command` must equal `testCommand`, including marker, plugin and
configuration options. Omit explicit test targets from that command to let
pytest discover the full suite normally and accept selected files in hook mode.
Changed `test_*.py` and `*_test.py` files run directly with those options.
Coverage flags in the command, `PYTEST_ADDOPTS`, or repository pytest configuration
trigger the full suite, preserving coverage thresholds. Discovery settings such
as `testpaths`, `python_files` and `norecursedirs` also retain the full command
so selected files cannot expand its suite. Custom configuration and
root-directory arguments also fall back to the full command.
References to a changed test module's name in other tracked Python files trigger
the full suite. Declare dynamically shared test modules in infrastructure globs
when their names are assembled at runtime. Changes to Python modules
or helpers fall back to `testCommand`: a matching test filename cannot establish
coverage of the module's callers.

For Node's built-in test runner or tsx, use a `node-test` mapping:

```json
{
  "kind": "node-test",
  "command": ["pnpm", "exec", "tsx", "--test"]
}
```

`command` must end in `--test` and prefix `testCommand`, for example
`["pnpm", "exec", "tsx", "--test", "tests/*.test.ts"]`. Explicit test files or globs
allow selection. A bare runner or directory targets retain the full command
because their default discovery patterns cannot be inferred safely. Glob `*`
matches one path segment; `**` matches across directory levels. Put runner options before
`--test`; only test paths or globs may follow it in `testCommand`. A direct Node
runner uses `["node", "--test"]`. Existing changed JavaScript or TypeScript files matching those targets run
directly, including test files without `.test` or `.spec` suffixes. Sources map to tests with the
same relative stem, ignoring `src`, `lib`, `test`, `tests` and `__tests__` directory
segments. For example, `src/format.ts` maps to `tests/format.test.ts` and
`src/format.spec.ts`. All matching tests within the full command's path/glob scope
are selected. The inventory expands configured filesystem targets, including
ignored generated tests. Unsupported glob syntax or a target with no matching
files retains the full command. These conventions do not infer a dependency graph; declare shared
helpers and dynamically loaded inputs in `sharedInfrastructureGlobs`. Deleted
files, unmatched sources, unknown inputs or unavailable test inventory run the
full command. With explicit file or glob targets, documentation-only changes skip tests.

For a per-file check without a unit suite, use `files`:

```json
{
  "kind": "files",
  "command": ["bash", "-n"],
  "include": ["*.sh"]
}
```

`include` is a nonempty list of checkout-relative globs. Matching is case-sensitive;
`*` spans directories, so `*.sh` also matches nested shell scripts. The hook runs
`command` once per matching existing changed file, appending its `./`-prefixed path
as one argument. It stops on the first failure. This handles commands such as
`bash -n` that accept only one file. Nonmatching changes skip this check. Deleting
a matching file or changing shared infrastructure runs `testCommand` instead.
Keep whole-repository lint or validation as `testCommand` for that fallback.

For validate, typecheck, build or asset checks that cannot be narrowed, use `full`:

```json
{
  "kind": "full",
  "reason": "Asset validation requires the complete repository."
}
```

`reason` must be a nonempty short explanation; there is no `command` field.
This kind always runs `testCommand`, including documentation-only or empty diffs.
It is the explicit affected check for repositories without a meaningful per-file
check, not an exception. It accepts the same optional preflight as all other kinds.
Unknown kinds or fields and missing or null mappings fail configuration validation.
Both `repository.py audit` and `validate` exit nonzero for a missing mapping.

The base is the merge-base of the pushed commit with `origin/<default branch>`.
The branch comes from `git.baseBranch`, with origin's remote HEAD as fallback.
Missing refs, shallow or disconnected history, and pushed commits other than the
checkout's HEAD trigger the full suite. Deletion-only pushes validate the current
checkout. Tracked working-tree changes participate in selection. Every hook run
prints the selected mode and its reason.

Shared infrastructure changes always trigger the full suite. Defaults cover
lockfiles, package manifests, Python packaging and requirements, configuration
and test setup filenames, tool pins, `.repo-standard*.json`, CI workflows,
hooks, scripts and policy. Patterns match repository-relative paths and basenames
at any depth. Add repository-specific patterns with
`development.sharedInfrastructureGlobs`, an optional list defaulting to `[]`.
These patterns extend the built-in defaults, for example `["shared/**", "fixtures/**"]`.

Only hook-mode Vitest receives `--maxWorkers` and `--testTimeout`. Workers default
to the process's available CPUs minus the one-minute load average, rounded down
with a floor of one. `VITEST_MAX_WORKERS` overrides that count. The timeout defaults
to 15000 milliseconds. `REPO_STANDARD_TEST_TIMEOUT` overrides it. Both overrides
must be positive integers. Direct-runner full-suite fallbacks preserve `testCommand` arguments
and receive the same hook limits, replacing existing worker and timeout CLI flags
to avoid duplicate options. An existing minimum-worker CLI flag is set to one so
it cannot exceed the hook's maximum. Hook invocations also set the legacy Vitest 3
thread and fork environment bounds to a minimum of one and the selected maximum.
This keeps pool-specific configuration from overriding the cap. Newer Vitest
versions use the CLI bound. No destination Vitest configuration is edited.
Wrapper fallbacks receive the pool environment bounds but keep their own CLI
options and timeout. Full checks and CI receive neither flag from this feature.

The current canonical `scripts/repository.py update` installs the managed helper,
check runner, hook and documentation. Each of the 21 repositories must explicitly
declare a mapping before validation or audit can pass. For an older version 2
configuration, choose the appropriate kind, commit that configuration change,
then run the template update. Do not silently insert `full` or keep local script
exceptions. Repository-owned test commands and infrastructure globs survive updates.
This contract was approved by Steve on 2026-11-11.

### Repository service diagnosis

Put read-only service checks in regular executable files under `.githooks/doctor.d/`.
`./scripts/setup --doctor` runs them in filename order from the checkout root,
after tool, dependency and hook checks. The first failure stops doctor and returns
nonzero. Normal setup does not run them. Use `mise exec --` inside a hook when it
needs pinned tools. Never install, deploy or mutate services from doctor hooks.
These repository-owned checks stay in review scope and survive canonical updates.

### Review scope in adopted repositories

The renderer derives exact managed paths from its output manifest for CodeRabbit
`reviews.path_filters` and Greptile `ignorePatterns`. Vendored scripts, the shared
hook, generated policy, provenance lock and other immutable canonical outputs
are reviewed in `sshickles/repo-standard`, not again in destination repositories.
Validation authenticates their source and rejects modifications to excluded files.
No managed-path exclusions are generated in the canonical repository itself.
The selected canonical revision is an operator-approved trust anchor. Provenance
checks consistency with that source; it does not independently authorize replacing
the validators and lock together. Owner rollout direction 12 places their review
in the canonical repository, so destination exclusions include both.

Repository instructions, `.repo-standard.json`, mise pins, application code,
repository CI workflows, custom scripts, `.githooks/pre-push.d/*` and
`.githooks/doctor.d/*` remain in scope. `t3.json` stays in scope because its runtime actions may vary by stack.
`AGENTS.md` and `.claude/settings.json` are canonical-managed outputs. Audit and
check reject any byte drift. Update replaces them exactly, removing all local
settings entries. The settings deny rules render the configured default branch,
including `master` or `dev`, deterministically. Put repository-specific guidance
in `docs/agents/repository.md`. Local review uses the model fallback when needed;
only required CI checks and the Greptile gate block merge. Recorded revisions
keep their original reviewer filters so existing installs can validate and
upgrade; update installs the new filters with the canonical agent files. Use the current
canonical updater to generate both reviewer configs; do not hand-copy ignore lists
or edit excluded runtime files. Put service-specific behavior in the owned hooks.

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
If an interrupted update changed canonical-managed files before refreshing the lock,
validation, audit and update reject that drift. Preserve the partial changes in a
commit, restore checked commands and all other canonical-managed files (including
managed documentation and helper scripts) to their last valid installed versions
matching the retained lock, commit that restoration, and retry from the selected
canonical checkout. An obsolete renderer may also leave reviewer configs without
the managed-path exclusions required by its recorded source. Preserve that partial
result, regenerate `.coderabbit.yaml` and `greptile.json` from the authenticated
recorded snapshot with the current canonical renderer, inspect and commit those
configs, then retry. The updater never silently repairs configuration drift.

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
collisions manually on the task branch before retrying. AGENTS.md and
`.claude/settings.json` are replaced exactly, including when they have drifted.
Exact agent-file validation also applies to older locks: previously allowed local
settings entries are drift and must be replaced by update. A newer canonical
revision alone still means "update available."
Other local integrations are preserved when the canonical file is unchanged between
the recorded and selected revisions. Shared commands and the hook still require
exact content from the recorded revision. The caller selects the
reviewed canonical revision; ancestry is not required because native squash
merging can replace the original source history. The updater writes the provenance lock last, after all other outputs succeed.
A successful apply is safe to rerun. After interruption, follow the recovery steps
above before retrying. Finish, check and review the diff,
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
shows an in-place update diff for an existing default-branch ruleset, including
one with a different name. It preserves unmanaged rule parameters and bypass
actors, and refuses ambiguous multiple targets. Existing-rule updates remain
preview-only; apply refuses them until manually reconciled. Reconcile
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

The manual worktree helper clears inherited Git repository variables while retaining
command-scope HTTP, credential, SSH, protocol and URL rewrite settings. It fetches and
uses the full configured remote-tracking ref, and refuses calls from another
repository's checkout. Short local branch or tag names cannot shadow its base.


Creation refuses an existing destination. After partial failure, retain the
created repository and local checkout, inspect the error, and resume adoption
or setup instead of rerunning creation or deleting work. Setup refuses an
unrelated hook manager and reports missing prerequisites without secret output.
Review tries the configured local profile without probing credentials, then runs
a model fallback if needed. It exits 0 for certified clean, 1 for findings and
2 when no reviewer could run or produce a verdict. Record unavailable review in
the PR and proceed; required CI checks and the Greptile gate control merge.

For worktree cleanup, check active users and processes, ignored/untracked files,
unpublished commits and the final PR head. Preserve uncertain data and remove
through the owning manager without force. Never reset or clean another task to
make adoption or an update pass.
