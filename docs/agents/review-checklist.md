# Review checklist

Review the full task diff against the fetched default branch and local changes.
Record base and head SHAs, the working diff digest if uncommitted, reviewer,
findings, fixes, verification and limitations. Review the updated diff again
before each push. Report a same-model fallback explicitly.

- Correctness: do commands and state transitions produce the intended behavior?
- Regressions: are existing callers, stack conventions and unrelated settings preserved?
- Security: are credentials protected, inputs validated and permissions enforced?
- Failure paths: do unavailable tools, partial work and unsafe conflicts fail clearly?
- Verification: do behavior tests cover changed contracts and real failure cases?
- Policy compliance: do generated policy, hooks, review and merge gates agree?

Run CodeRabbit first. If it is missing, fails, times out or returns an incomplete
or uncertified result, `./scripts/review` runs an independent model reviewer.
Prefer a distinct base model and report a same-model fallback. Set
`REPO_STANDARD_IMPLEMENTER` to the implementer's provider or model so automatic
selection can prefer a different model family. If it is unset, independence is
reported and recorded as unverified. Supply this checklist, AGENTS.md
and the complete diff. Fix findings and rerun until clean for the updated commit.
Do not attempt browser login over SSH after an authentication failure.

The command exits 0 for certified clean, 1 for findings and 2 when no reviewer
could run or produce a verdict. It prints the reviewer and saves base, head,
diff digest and verdict in the worktree's Git directory as
`repo-standard-review.json`. Local review never blocks push or PR creation.
If no reviewer could run, record that in the PR and proceed. Only required CI
checks and the Greptile gate block merge.

`REPO_STANDARD_CODERABBIT_TIMEOUT` sets CodeRabbit's timeout in seconds (600 by
default). `REPO_STANDARD_REVIEW_FALLBACK_TIMEOUT` sets the model timeout (900 by
default). `REPO_STANDARD_REVIEW_FALLBACK` selects a command name or full argv
command, parsed without a shell. Codex and Claude receive non-interactive,
read-only flags. Other commands must be read-only, non-interactive adapters
accepting the review prompt on stdin. The final output line must be
`REVIEW: CLEAN` or `REVIEW: FINDINGS <n>` with a positive count and findings above.
