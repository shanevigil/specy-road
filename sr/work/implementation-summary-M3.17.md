# Implementation summary — M3.17

## Summary

Failing verifier rows in the executor's `READY-<agent>.md` now fail the review gate until every failing command is named in `verify_pre_existing` on at least one **approving** review record. `handoff status`, `mark-implementation-reviewed`, and `finish-this-task` (via `gate_holds_at_head_or_exit`) all use the same `evaluate_gate` result, so `policy_met` and refusal paths stay aligned. Empty `verify` remains a reported note only.

## Touch zones (confirmed)

`specy_road/review_gate.py`, `specy_road/review_files.py`, `specy_road/bundled_scripts/review_cli.py`, `specy_road/bundled_scripts/mark_implementation_reviewed.py`, `specy_road/schemas/`, `specy_road/templates/specyrd/`, `docs/orchestration.md`, `tests/`

Also updated `specy_road/bundled_scripts/mark_implementation_reviewed.py` (gate evaluation with branch + READY) and `specy_road/templates/project/work/review-record.template.md` (schema lives under `specy_road/schemas/` only).

## Verification

```bash
pytest tests/test_review_evidence.py tests/test_mark_implementation_reviewed_gate.py tests/test_review_gate.py tests/test_review_signing.py tests/test_review_hardening.py tests/test_prerelease_review.py -q
```

## Added

- `failing_verifier_entries` — list non-zero READY verify rows for gate logic.
- `pre_existing_cmds_from_approvals` — union of `verify_pre_existing` from counted approving reviews only.
- `verifier_gate_problems` — problem strings for unmarked failing READY verifiers.
- `non_gating_verify_problems` — empty-verify note for handoff status without duplicating gate lines.
- `GateResult.verifier_problems` and inclusion in `passed` / `problems()` — gate fails until verifiers are marked or pass.
- `evaluate_gate(..., branch=)` — loads the registered branch's READY when scoring verifier problems.
- `human_approval_completes` guard on `verifier_problems` — interactive human cannot bypass unmarked failures.
- `verify_pre_existing` on `review-record.schema.json` — optional string array on review records.
- Tests `test_failing_verifier_blocks_even_when_reviews_pass`, `test_pre_existing_marker_on_approve_clears_verifier_block`, `test_pre_existing_marker_on_block_is_ignored` — acceptance A3.
