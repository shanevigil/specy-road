# Implementation summary — M3.17

## Summary

Failing verifier rows in the executor's `READY-<agent>.md` now fail the review gate until every failing command is named in `verify_pre_existing` on at least one **approving** review record. `handoff status`, `mark-implementation-reviewed`, and `finish-this-task` (via `gate_holds_at_head_or_exit`) all use the same `evaluate_gate` result, so `policy_met` and refusal paths stay aligned. Empty `verify` remains a reported note only.

Merged `origin/WIP/improvements-0-3-1` (M4.17 escalation): `handoff status` still reports `loop.problems()` and `escalated`, and `review list` still prints the escalation line, while verifier problems stay on `evaluate_gate`.

Sol review (gpt-6.1-sol): removed the unreachable `verdict != "approve"` filter in `pre_existing_cmds_from_approvals` (`evaluate_gate` already passes only `result.approvals`) and the `not ready.ok` disjuncts (`latest_ready` only returns valid files). None handling is kept.

## Touch zones (confirmed)

`specy_road/review_gate.py`, `specy_road/review_files.py`, `specy_road/bundled_scripts/review_cli.py`, `specy_road/bundled_scripts/mark_implementation_reviewed.py`, `specy_road/schemas/`, `specy_road/templates/specyrd/`, `specy_road/templates/project/work/review-record.template.md`, `docs/orchestration.md`, `tests/`

Planning sheet Approach filled under `sr/planning/` (requested after the first review round).

## Verification

```bash
pytest tests/test_review_evidence.py tests/test_mark_implementation_reviewed_gate.py tests/test_review_gate.py tests/test_review_signing.py tests/test_review_hardening.py tests/test_prerelease_review.py tests/test_review_rca.py tests/test_review_cli.py -q
```

## Added

- `failing_verifier_entries` — list non-zero READY verify rows for gate logic.
- `pre_existing_cmds_from_approvals` — union of `verify_pre_existing` from counted approving reviews.
- `verifier_gate_problems` — problem strings for unmarked failing READY verifiers; `ready is None` is the no-READY path.
- `non_gating_verify_problems` — empty-verify note for handoff status; `ready is None` skips it.
- `GateResult.verifier_problems` and inclusion in `passed` / `problems()` — gate fails until verifiers are marked or pass.
- `evaluate_gate(..., branch=)` — loads the registered branch's READY when scoring verifier problems.
- `human_approval_completes` guard on `verifier_problems` — interactive human cannot bypass unmarked failures.
- `verify_pre_existing` on `review-record.schema.json` — optional string array on review records.
- Tests `test_failing_verifier_blocks_even_when_reviews_pass`, `test_pre_existing_marker_on_approve_clears_verifier_block`, `test_pre_existing_marker_on_block_is_ignored` — acceptance A3.
- Tests `test_no_ready_file_does_not_add_verifier_problems`, `test_empty_verify_is_reported_but_does_not_block_with_an_approval` — remaining None / empty-verify paths after dropping unreachable `not ready.ok` and non-approve filters.
