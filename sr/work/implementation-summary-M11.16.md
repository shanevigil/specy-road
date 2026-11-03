# Implementation summary: M11.16 — sheet-edits-keep-approvals

## What changed

When `git diff <reviewed>..<HEAD>` touches only this leaf's planning sheet,
`work/implementation-summary-<NODE_ID>.md`, or paths under
`work/reviews/<NODE_ID>/`, `evaluate_gate` still counts review records filed at
the earlier commit. `GateResult.summary()` and `handoff status` report that
carry in the policy line. Any other path in the range keeps today's stale
behaviour.

## Touch zones (confirmed)

- `specy_road/review_gate.py` — carry flag, stale bypass, policy summary text
- `specy_road/review_files.py` — `only_planning_or_review_bookkeeping_since`
- `docs/orchestration-review.md` — documented exempt delta
- `tests/test_sheet_edits_keep_approvals.py` — A1/A2 coverage

## Verification

- `pytest tests/test_sheet_edits_keep_approvals.py`
- `specy-road file-limits`

## Added

- `only_planning_or_review_bookkeeping_since` in `review_files.py` — path set check for approved..commit
- `GateResult.bookkeeping_carry` — drives the policy-line carry message
- `evaluate_gate` branch — skips stale when the bookkeeping-only delta holds
- `tests/test_sheet_edits_keep_approvals.py` — sheet-only, summary-only, mixed, and handoff status cases
