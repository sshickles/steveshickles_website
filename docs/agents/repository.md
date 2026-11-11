# Repository details

## Purpose and architecture

`sshickles/steveshickles_website` is Steve Shickles's static personal website.
`index.html` contains the main page and inline styles/scripts; `error.html` is
an error page. `CNAME` declares steveshickles.com. There is no package manager,
application build, backend or dependency lockfile. Steve owns content and hosting.
Check existing issues, assignees and PRs before claiming work; no readiness label
is required. The default branch is `dev`.

## Commands and tool versions

Use `./scripts/setup`, `./scripts/check`, `./scripts/test` and `./scripts/review`.
Linux is the only supported development platform. Git, Python 3.11+ and mise are
host prerequisites. `mise.toml` pins actionlint 1.7.12, the only installed tool.
There are no Node or package-manager requirements. The custom-stack setup adapter
uses mise.toml as its exact version manifest and exposes the verified actionlint
executable at ignored `.cache/tools/actionlint`; there are no application
dependencies. The canonical generator currently requires this adapter even for
a dependency-free static site. Review tries the configured local CodeRabbit runner first, then an independent
model reviewer if needed. Local review does not block push or PR creation;
required CI and the Greptile gate control merge. CI runs `./scripts/setup --ci`, then `./scripts/check` in the `checks` job.

## Configuration ownership

`.repo-standard.json` owns repository identity, `origin/dev`, validation and review
configuration. `.repo-standard-source.json` records canonical provenance.
GitHub owns live rulesets and Pages settings; reviewer dashboards own their live
integration settings. Committed reviewer configuration does not prove dashboard
state. No secrets or environment files are needed. `CNAME` and
`.github/workflows/static.yml` own the existing deployment inputs.

## Local runtime setup

Run `./scripts/setup`, then `./scripts/setup --doctor` on the assigned Linux host.
Setup installs actionlint and selects `.githooks`; it does not deploy. Open the
HTML files locally to inspect content. Reuse the assigned T3 worktree and its
branch; use T3's managed worktree workflow for new isolated tasks. Committed
`t3.json` supplies command definitions without changing saved T3 settings.

## Verification

`./scripts/check` validates canonical policy integrity and structure, runs
`./scripts/test`, actionlint and shell syntax validation. The default branch has
no application test suite. `./scripts/test` honestly runs repository policy
validation; it does not claim browser, HTML rendering or application coverage.
This minimal suite suits a static site and adds no artificial application tests.
The shared pre-push hook rejects pushes to `dev` and runs fast validation plus
affected-test selection against the merge base with `origin/dev`. This custom
policy-validation suite has no supported affected-test mapping, so hook mode
retains the full `testCommand`. No extra shared-infrastructure globs are needed.
`./scripts/check` without arguments and CI still run the full suite. There
were no existing repository hooks or setup commands to migrate. Future custom
hook responsibilities belong in executable `.githooks/pre-push.d/` entries.
Use the shared review checklist and fix valid local and PR review findings.

Apply canonical updates from the reviewed source checkout on a clean task branch:

```sh
python3 /src/sshickles/repo-standard/scripts/repository.py update "$PWD" \
  --source /src/sshickles/repo-standard --revision <approved-sha> --apply
```

## Deployment and recovery

The existing `static.yml` deploy job remains unchanged: ubuntu-latest, existing
action versions, pushes to `master` and manual dispatch. Adoption into `dev`
does not change that deployment trigger. Site HTML and domain files are preserved.
Production deployment requires explicit owner authorization. Historical DNS and
Pages setup details are in `GITHUB_PAGES_SETUP.md`; inspect current GitHub settings
before changing them. Recover content through a reviewed revert PR. Preserve
unpublished work and remove worktrees only through their owning manager after
checking active users and tracked, untracked and ignored files.

## Approved exceptions

None.
