# Implementation summary: M11.16 — sheet-edits-keep-approvals

## What changed

When `git diff <reviewed>..<HEAD>` touches only this leaf's planning sheet,
`work/implementation-summary-<NODE_ID>.md`, or paths under
`work/reviews/<NODE_ID>/`, `evaluate_gate` still counts review records filed at
the earlier commit. `GateResult.summary()` and `handoff status` report that
carry in the policy line. Any other path in the range keeps today's stale
behaviour. A merge in `approved..commit` (`git rev-list --merges` non-empty)
is new work even when the tree equals the first parent (`git merge -s ours`).
An unresolved `commit` (falsy) leaves records stale, as before this leaf.

The helper lives in `specy_road/review_bookkeeping.py` so `review_files.py` and
`review_gate.py` keep the comments and docstrings they had before this leaf.

## Touch zones (confirmed)

- `specy_road/review_bookkeeping.py` — helper (added; brief §7)
- `specy_road/review_gate.py` — carry flag, stale bypass, policy summary text
- `specy_road/review_files.py` — unchanged from before this leaf
- `docs/orchestration-review.md` — documented exempt delta
- `tests/test_sheet_edits_keep_approvals.py` — A1/A2 coverage

## Verification

- `pytest tests/test_sheet_edits_keep_approvals.py`
- `specy-road file-limits`

## Added

- `specy_road/review_bookkeeping.py` — new module so the helper does not eat comments in the 400-line files
- `only_planning_or_review_bookkeeping_since` — path set check; False when `commit` is falsy or the range contains a merge
- `count_at_later_commit` — evaluate_gate wiring so review_gate stays at 400 lines
- `CARRY_NOTE` — policy-line suffix when approvals still count
- `GateResult.bookkeeping_carry` — drives that suffix
- `tests/test_sheet_edits_keep_approvals.py` — sheet-only, summary-only, mixed, ours-merge, unresolved commit, handoff status
- `test_ours_merge_stales_approval` — approve then `git merge -s ours` leaves the record stale
- `test_unresolved_commit_leaves_approval_stale` — `evaluate_gate(..., None)` does not carry
