<!-- Generated. Do not edit. -->
Canonical repository: sshickles/repo-standard
Canonical revision: eb89de12a414b97a8862cd8496113bcfe3f0e6ee
Canonical source: policy/policy.md
SHA-256: 04e97c653c3aa1c7fffc2fb85e2f2e335eb26bec4e184517304ab62da8abbd32

# Shared engineering policy

## Authority and boundaries

For assigned engineering work, proceed through implementation, checks, review,
commit, push, ready PR creation, native squash auto-merge and follow-through
until merged unless the owner explicitly pauses work. Only the owner can
unpause a PR they paused. A narrower task instruction controls its scope.

Development and production use the same required checks. Production deployment,
configuration and access do not require extra approval solely because they affect
production. Ask for material missing decisions, unclear scope, exact changes to
live GitHub merge settings, unrequested irreversible actions such as deleting
production data, or unrelated new spending or external data sharing.
Configured, authorized model API usage, including metered usage, is authorized.

Command permissions approve command forms, not work in unassigned repositories.
Before a GitHub write, verify the target against the owner's assigned scope.
Permission adapters are not repository access boundaries and do not expand
the owner's authorization.

Never bypass platform permissions, provider controls or merge requirements.
Never manually merge, use an admin merge bypass, force-push a published branch
or push directly to the protected default branch. This policy supersedes older
conflicting repository and host workflow instructions. Preserve unrelated rules
and report executing-platform constraints that repository settings cannot change.

## Canonical documentation

The canonical policy and template are maintained in `sshickles/repo-standard`.
Read `AGENTS.md`, this generated `docs/agents/policy.md` and the local
`docs/agents/repository.md` before working. The generated header records the
canonical source revision and digest. Validate it through `./scripts/check`.
Do not edit generated policy or its checksum to create a local exception.

Repository instructions have seven sections: purpose and architecture; commands
and tool versions; configuration ownership; local runtime setup; verification;
deployment and recovery; approved exceptions. Only explicit owner-approved
exceptions override shared policy. Record reason, scope and approval reference.
Pre-existing contradictions are not exceptions.

Keep `AGENTS.md` and `.claude/settings.json` byte-identical to their canonical
renderings. Only repository identity and default-branch substitutions may vary;
no repository-specific settings entries survive updates. Repository-specific
guidance belongs in `docs/agents/repository.md`. This exact-match requirement
also applies when auditing older locks that previously allowed local settings
entries (owner approval: Steve, 2026-11-11); update replaces those entries.

Keep other instruction files as thin adapters to `AGENTS.md`. Preserve necessary
tool configuration and useful product, architecture and operational docs. Move
local details to repository instructions or linked docs and delete duplicate
workflow prose. Audit applicable host and user instructions during rollout,
including installed workflow and routing preferences, preserving unrelated
preferences. Do not change other hosts or tasks outside the assigned scope.

## Models and delegation

Keep the user-selected lead model and reasoning setting. Discover available
models and capabilities for each task rather than maintaining fixed routing
names. Choose suitable delegates and reasoning effort for complexity and risk;
escalate when uncertainty or failed attempts justify it.

Use configured, authorized providers, including metered APIs. Do not impose
agent-managed budgets, cost approvals, spending reservations, concurrency caps
or delegation-depth limits. The owner manages spending externally. Parallel and
nested delegation are useful when work is independent; choose concurrency from
resources and coordination needs, respecting actual platform limits.

Give concurrent coding tasks separate worktrees and runtime resources. Pass
policy, local instructions, scope and acceptance criteria to each delegate.
If a preferred model or effort is unavailable, use the best suitable available
alternative and report material substitutions. Use another authorized provider
when possible if one blocks usage; never bypass provider controls. The lead
owns integration, verification and the result. Delegation adds no authority.

Independent review requires a reviewer who did not implement the change and a
distinct base model where available. Another account, context or reasoning
setting does not establish independence. The provider may be the same. If no
different model is available, use a separate same-model reviewer and report the
fallback. Implementer self-review cannot silently replace independent review.

## Workspace and implementation

Use a task-specific worktree and reuse it when resuming. Prefer the host's
supported worktree manager; use the documented Git fallback when unavailable.
Fetch and start independent work from the latest remote default branch, using
its actual name. For Git fallback, specify an explicit start point and place
worktrees outside existing checkouts. Never start another agent just to obtain
a checkout. See repository instructions for supported adapters and commands.

Merge the latest default branch into published task branches when needed.
Never rebase or force-push a published branch. Preserve unrelated edits and
other tasks' workspaces. Do not stash, copy, reset or delete unrelated work to
establish isolation. Ask only if existing work prevents progress.

Use a brief plan for nontrivial work and proceed. Reproduce defects where
practical, fix root causes and include nearby cleanup when checks can verify it.
Necessary dependency and architecture changes are authorized within scope;
do not expand a workflow rollout into unrelated product changes.

## Common commands and setup

Every repository exposes executable `./scripts/setup`, `./scripts/check`,
`./scripts/test` and `./scripts/review`. Keep stack conventions underneath and
pin tools consistently across hosts. Linux is the only supported development
platform. Use the assigned Linux hosts and explicitly report unsupported capabilities.

Setup is safe to rerun, installs locked dependencies and configures committed
hooks. Preserve local work and configuration. Install needed tooling where
access permits, using versioned installations when global upgrades would
conflict. Report missing access or prerequisites without secrets. Setup must
never deploy as a side effect. Production labels do not create a separate
setup approval gate; all initializers must be idempotent and non-deploying.

Check runs all required locally executable validation, including tests and
policy integrity. CI calls it without arguments and keeps the full suite as
the required merge gate. Pre-push uses its hook mode for fast checks and affected
tests, with conservative full-suite fallbacks. External Greptile checks remain
separate. Test runs the documented suite. Review runs CodeRabbit first; if it is
missing, fails or times out, it runs an independent model reviewer (Codex, Claude or similar, distinct base model where
available). It exits 0 when a reviewer certifies the change clean, 1 for findings
and 2 when no reviewer could run; it never silently skips review.

## Checks, hooks and review

Run documented checks and add meaningful behavior tests for changes where
practical. Investigate failures and retry with evidence of flakiness; fix
in-scope failures or report the blocker. Never bypass hooks or weaken checks
to make a push succeed. Hook-mode Vitest uses load-aware workers and a longer
test timeout, with explicit environment overrides. Full checks and CI do not
receive these hook limits.

Commit and install a pre-push hook that runs `./scripts/check --pre-push`, preserves
existing responsibilities and rejects the protected default branch by its
remote destination ref from stdin, regardless of the local branch name. Run checks for ref deletions too.
Hook mode runs policy integrity, lint, type checking and configured non-test
validation, then affected tests from the pushed commit's merge-base with the
origin default branch. Missing history, shared infrastructure changes and stacks
without an affected-test mapping run the full test command. Repository-owned
pre-push checks still run after the common checks.

Prefer `~/.local/bin/cr-auto` or the appropriate configured
`cr-as <bbl|pp|rsp|ss|wca>` profile. Discover equivalent supported host setup.
Report authentication failures without credentials and never attempt browser
login over SSH. If CodeRabbit is missing, fails, times out or cannot certify a
complete result, run an authorized independent model reviewer under the
independence rules above. Iterate until that reviewer certifies the updated
commit clean. Follow the shared
[review checklist](review-checklist.md) for correctness, regressions, security,
failure paths, meaningful verification and policy compliance.

Fix findings and repeat review until clear. Resolve disputed findings with
evidence. Review the updated change before every push and record fallback use.
A successful process exit alone does not prove a clean review transcript. Record what was reviewed and remaining limitations.

Local review never blocks push or PR creation. Fix findings from a reviewer
that ran. If no reviewer could run, record that in the PR and let Greptile do
the final review. Only required CI checks and the Greptile gate block merge.

## PR and merge workflow

1. Complete local checks and local review (CodeRabbit, or the model reviewer fallback).
2. Commit and push through the installed hook.
3. Open a ready PR. Verify that server-side protections enforce the required
   checks and current-head Greptile 5/5 approval, then immediately enable native
   squash auto-merge with `gh pr merge <number> --auto --squash`. If either gate
   is missing, leave the PR open until the approved configuration is in place.
4. Require Greptile's 5/5 approval and passing review check for the current head.
5. Monitor until GitHub reports `MERGED`.

Fix failing required checks and verified findings, repeat local review before
each later push, answer and resolve every review thread, and explain disputes
with evidence. Never claim another reviewer's approval. Merge the default
branch into the task branch as needed. If auto-merge clears, fix the cause and
re-enable it unless the owner paused it. Disable queued auto-merge when paused
with `gh pr merge <number> --disable-auto`; only the owner can unpause it.

Use supported persistent monitoring. If unavailable, report the pending state
and exact resume steps. Do not claim completion while a PR remains open.
GitHub performs the merge after requirements pass. Never manually merge, use
admin bypasses or weaken protections to unblock it. Record current-head review,
check and native auto-merge evidence, not just a merged commit.

## GitHub and review configuration

Target `allow_auto_merge: true`, `allow_squash_merge: true` and
`delete_branch_on_merge: true`. An active `~DEFAULT_BRANCH` ruleset requires
deletion protection, non-fast-forward protection and pull requests with squash
as the allowed merge method, one approval, stale approvals dismissed and all
review threads resolved. Require actual reliable CI check names and
`Greptile Review`, preserving relevant integration bindings. Missing CI or
Greptile is a rollout blocker. Deployment checks are informational.

Before changing live settings, inspect repository and inherited rulesets plus
legacy protection. Present exact changes, including removal of deployment
requirements, for owner batch approval. Preserve bypass actors and unrelated
protections, prefer updating applicable rulesets and report drift. File changes
and audit proposals never authorize live settings writes.

Configure `greptile.json`: `autoApprove.enabled: true`,
`autoApprove.filters.includeRepositories` scoped to this repository,
`autoApprove.riskCeiling: "critical"`, `statusCheck`, `includeConfidenceScore`
and `triggerOnUpdates` true, and `triggerOnDrafts` false. Its `$comment` explains
native squash auto-merge after required checks and current-head 5/5 approval.
Separately verify dashboard confidence-to-pass 5 and repository auto-approval;
file configuration cannot prove dashboard state. Automatic CodeRabbit PR
reviews stay disabled in `.coderabbit.yaml`.

Permission adapters permit native squash auto-merge and disabling it, deny
admin bypasses, preserve force-push and default-branch push restrictions and
have no blanket merge deny shadowing authorized flow. Verify actual adapter
syntax and deny precedence. Replace production-only approval restrictions.

## Configuration and communication

Keep secrets and environment configuration in each service's authoritative
store and document ownership. Pulled environment files are generated artifacts,
never hand-maintained sources of truth. Never commit credentials or print
resolved secrets. Use only providers authorized for the task's data; model
selection does not authorize unrelated data sharing.

Use plain concise prose, sentence-case headings and straight quotes. Avoid
em dashes, filler, decorative emoji and chatbot phrasing. Do not name tools or
models used to write commits or PR descriptions. Give brief updates on findings,
decisions and blockers. Ask material questions with a few concrete options and
continue independent work while waiting. Report checks actually run, results,
PR and merge evidence, limitations and pending work accurately.

Weekly and canonical-change audits report updates and planned diffs. A newer
revision is update-available, not local drift. Apply updates explicitly on a
clean task branch, preserve unrelated work and use one rollout PR per repository,
updating that PR on reruns. Automation follows the same review and merge gates
and never applies live GitHub settings without approved scope.
