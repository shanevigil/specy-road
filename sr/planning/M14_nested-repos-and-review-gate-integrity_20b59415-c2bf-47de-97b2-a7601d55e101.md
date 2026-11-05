## Intent

Make the review gate and the worktree tools trustworthy in projects that keep code in separately versioned repositories under the project root, and make reviewer evidence and cost visible. A worker-orchestration run in a consumer repo whose code lives mostly in gitignored sibling repositories (with `nested_repos` not configured) found that a stale approval still counted after sibling-only code changes, that doctor offered to remove a live leaf's worktree, that worktree prune would delete sibling worktrees, and that adopting `nested_repos` was blocked because landing always pushes. The same run, and this toolkit's own run, showed one reviewer approving quickly with no probe while another found real defects, with reviewer token use invisible.

## Approach

- **Integrity first.** M14.1 (approval carry across sibling repos) has no dependencies and is the highest priority; it also supplies `specy_road/sibling_repos.py`, which M14.4.2 and M14.4.3 reuse.
- **Destructive tools stay safe.** M14.2 (doctor) and M14.3 (worktree prune) refuse to touch anything live or belonging to another repository.
- **Adoptable nested_repos.** M14.4 lets a project land and base nested repos locally or by hand, and gives packet and worker checks sight of siblings that are not configured.
- **Evidence and cost.** M14.5 flags an approve with no recorded probe; M14.6 makes reviewer usage visible; per-model block rates are M12.4.3, beside the per-area scores in M12.4.1.
- **Session end.** M14.7 fixes `session end` picking no session when the user has several live ones (the derived id changes between a harness's shell calls).
- Every file near the 400-line cap is paired with a new sibling module in its leaf's touch zones.

## Tasks / checklist

- [ ] M14.1 — approvals never carry across unreviewed sibling changes; validate warning.
- [ ] M14.2 — doctor leaves live worktrees and commit-less branches alone.
- [ ] M14.3 — worktree prune refuses other repositories' worktrees.
- [ ] M14.4 — nested_repos local landing/base, sibling diffs, sibling checks.
- [ ] M14.5 — approve without a probe flagged; optional policy.
- [ ] M14.6 — review usage; RUN logs per round.
- [ ] M14.7 — session end resolves by worktree and branch.
- [ ] M14.8 — implementation-zone check at ready and review delegate; sibling-aware; validate warning.
- [ ] M14.9 — `review rca` launcher; no-analyst outcome; usage limits recorded as unavailable.
- [ ] M14.10 — convergence-aware escalation and findings trend.
- [ ] M14.11 — rework/fix-round prompt audits the failure class and lists probes.
- Out of scope: a default strong_review for numeric zones (see M14.5), and configuring nested_repos automatically.

## References

- Roadmap chunk for `M14` (`roadmap/phases/M14.json`)
- `specy_road/review_bookkeeping.py`, `specy_road/nested_repos.py`, `specy_road/worktree_prune.py`, `specy_road/bundled_scripts/doctor.py`
- `docs/git-workflow.md` (nested_repos), `docs/orchestration-review.md`
- No `shared/` contract applies.
