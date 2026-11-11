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

If CodeRabbit is unavailable or authentication fails, do not log in through a
browser over SSH. Use an authorized independent review tool or a separate
reviewer who did not implement the change. Prefer a distinct base model and
report when only a same-model reviewer is available. Supply this checklist and
the complete diff. Keep the review evidence in the task record. The review
command exits nonzero when it cannot certify a local review; external fallback
evidence must be reported separately, never converted into a silent success.
