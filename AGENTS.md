<!-- Generated from sshickles/repo-standard@1f6fb1d4ca95dc0bef5c59b5a95298e8a3907e83. Do not edit. Rules come from the canonical policy; facts come from .repo-standard.json. -->
# Agent instructions

These rules are the same in every repository and for every coding agent. They
are maintained in `sshickles/repo-standard`. Repository facts follow the rules.

## Scope and authority

The T3 task prompt is the scope. Read a GitHub issue only when the prompt links
it. Take assigned work through implementation, checks, review, commit, push, a
ready PR, native squash auto-merge and follow-through until GitHub reports it
merged, unless the owner pauses the work. Only the owner unpauses it.

Ask before material missing decisions, unclear scope, irreversible actions the
prompt did not request, or new spending and external data sharing. Offer a few
concrete options and continue independent work while waiting. Configured model
and service usage is authorized; do not impose budgets, cost approvals or
concurrency caps of your own. Delegation and command permissions add no
authority, and a task in one repository does not authorize writes to another.

## T3 Code

All development runs in T3 Code on the assigned Linux hosts. There is no local
development and no other worktree manager. T3 creates one worktree per task from
the latest default branch and runs `./scripts/setup` on creation; reuse that
worktree for the whole task. If tools or dependencies are missing, run
`./scripts/setup` yourself. `t3.json` defines four actions: setup, check, test
and review, each calling the script of the same name.

Give concurrent tasks separate worktrees. Merge the default branch into a
published task branch when needed; never rebase or force-push it. Preserve
unrelated edits and other tasks' work: do not stash, reset or delete them.
After opening a PR, watch it until it merges.

## Production

Production changes only through merges. A deploy that follows the normal merge
path needs no confirmation. Never act on production directly: no
`vercel --prod`, no `convex deploy --prod`, no production function runs, data
edits or environment variable changes. Work that must touch production ships as
code, such as an internal function, and the owner runs it.

## Checks

Local checks are quick and scoped to the change. CI is the safety net: it runs
everything on every PR, so do not run the full suite locally unless a failure
needs it.

- While working, run `./scripts/check`. It checks instruction integrity, lints
  and type-checks the files you touched, and runs the tests related to them.
- On commit, the pre-commit hook formats and lints the staged files only.
- On push, the pre-push hook only rejects pushes to the default branch.
- On the PR, CI runs the full suite as parallel jobs: lint, type checking, all
  tests and the build.

`./scripts/setup` installs pinned tools, locked dependencies and the Git hooks,
and attaches configured development services. It is safe to rerun and never
deploys. `./scripts/check --all` and `./scripts/test` run the full suite when
you need it. Never bypass hooks or weaken a check to make a commit or push
succeed.

## Implementation

Make a brief plan for nontrivial work and proceed. Reproduce defects where
practical and fix root causes. Prefer the smallest coherent change. Add
behavior tests for changed behavior. Dependency and architecture changes needed
for the task are in scope; unrelated product changes are not. Investigate
failing checks: fix failures in scope and report blockers with evidence.

Keep the lead model and reasoning setting the owner selected. Delegate
independent work when useful, pass these instructions, the scope and the
acceptance criteria to each delegate, and stay responsible for the result.

## Review

One reviewer reviews each change: Greptile, on the PR, while CI runs. Do not run
a local review first. `./scripts/review` exists for when the owner asks for one.

The reviewer checks six things:

- Correctness: commands and state changes produce the intended behavior.
- Regressions: existing callers, conventions and unrelated settings still work.
- Security: credentials are protected, inputs validated, permissions enforced.
- Failure paths: unavailable tools, partial work and conflicts fail clearly.
- Verification: tests cover the changed behavior and real failure cases.
- Policy: the change follows these instructions and keeps the merge gates.

Fix the real defects the reviewer finds. Answer a style preference or a
speculative suggestion with a short reply instead of a code change, and
disputed findings with evidence. Never claim a reviewer's approval.

## Pull requests and merge

1. Pass `./scripts/check`.
2. Commit and push through the installed hooks.
3. Open a ready PR. Confirm the default branch requires the CI checks and
   Greptile, then enable native squash auto-merge at once:
   `gh pr merge <number> --auto --squash`. If either requirement is missing,
   leave auto-merge off and report it.
4. Watch the PR. Fix failing required checks and real Greptile findings, and
   resolve every review thread.
5. GitHub merges when the required CI checks pass and Greptile approves the
   current head with 5/5. Stop only when GitHub reports `MERGED`.

Required CI and the Greptile 5/5 approval are the only merge gates. Never merge
manually, use an admin bypass, or push to the default branch. If auto-merge
turns off, fix the cause and enable it again, unless the owner paused the PR;
then leave it off (`gh pr merge <number> --disable-auto`). Do not claim the
work is complete while its PR is open.

## Generated files and protections

`AGENTS.md`, `CLAUDE.md`, the agent settings under `.claude/`, `.codex/` and
`.gemini/`, the shared scripts, the Git hooks, the CI workflow, the review
configuration and `.repo-standard-source.json` are generated from
`sshickles/repo-standard`. Do not edit them; `./scripts/check` rejects any
difference. To change a fact, edit `.repo-standard.json` and run
`python3 scripts/standard.py render`.

Do not add instruction files: no other `AGENTS.md`, `CLAUDE.md` or `GEMINI.md`,
and no skills, agent rules or plugin manifests besides the product plugins
listed in the facts. The check fails on them. Skills are installed on the
hosts and describe how to do a task; on checks, review and merging, these
instructions win. A document may
state a rule about this repository's code only when a command in
`./scripts/check` enforces it and the facts list both.

Do not change live GitHub settings, rulesets or required checks unless the
owner approved that exact change, and never bypass a protection.

## Configuration and secrets

Each service's own store holds its configuration and secrets. Pulled
environment files are generated artifacts: never edit them by hand, commit them
or print their values. Never commit credentials.

## Communication

Write plain, concise prose with sentence-case headings and straight quotes. No
em dashes, filler or decorative emoji. Do not credit an agent, tool or model
as the author in commits or PR descriptions, and add no co-author or "generated
with" lines; the review record may name its reviewer. Do not save agent memory;
these instructions are the only standing context.
Report the checks you ran and their results accurately, including what failed
or was skipped.

## Repository facts

Rendered from `.repo-standard.json`. These are facts about this repository, not rules.

- Repository: `sshickles/steveshickles_website`. Steve Shickles's static personal website: index.html, error.html and a CNAME for steveshickles.com. No build, backend or packages.
- Default branch: `dev` on remote `origin`.
- Required checks: `checks`, `Greptile Review`.
- Validation in `./scripts/check`: `actionlint`, `bash scripts/lint-shell`.
- Test suite: `python3 scripts/standard.py validate .`.

### Deployments

- Website: GitHub Pages, production, push to master or manual run of static.yml, which uploads the whole repository root; a merge to dev does not publish, https://steveshickles.com

### Services

- GitHub Pages: Hosts the site published from master; CNAME sets the custom domain steveshickles.com.
- GitHub Actions: Runs the required checks job on PRs and the static.yml Pages workflow on master.
- Greptile: Reviews every PR; its approval is a required check.
