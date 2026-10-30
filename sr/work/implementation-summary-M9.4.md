## Summary

Leaf M9.4 adds an optional `blocked_on` list to READY hand-offs so executors can stop when an acceptance criterion would require weakening tests or raising baselines/caps, without bypassing the review gate. Schema validation, semantic checks against brief acceptance ids, handoff status (`executor_blocked`), and gate refusal are wired through the existing review pipeline.

This revision answers the three required changes in `REVIEW-gpt-6.1-sol.md` (block at `e9d0b5e`):

1. `executor_blocked` now outranks `blocked` and `escalated` in `handoff status` when the current READY declares `blocked_on`; the reviewer block and escalation stay listed in `reviews` / `escalation` / `problems`.
2. The gate's executor-blocked problems bind to the commit under review (`same_commit`): a `blocked_on` READY for an earlier commit does not defeat approvals for a later implementation commit.
3. The finish refusal test drives the public `finish-this-task` entry point (`finish_task.main`) instead of the private `_impl_review_or_exit`.

## Changes

- `specy_road/schemas/handoff.schema.json` — optional `blocked_on` array with `acceptance` (`A<n>`) and non-empty `reason`.
- `specy_road/templates/project/work/handoff-ready.template.md` — commented example for `blocked_on`.
- `specy_road/review_files.py` — `ready_semantic_errors` validates acceptance ids; helpers for gate and handoff display.
- `specy_road/review_gate.py` — `evaluate_gate` appends `executor_blocked_gate_problems` only when the READY commit is the commit under review.
- `specy_road/bundled_scripts/review_cli.py` — `_node_status` computes blocked lines for a current READY and picks `executor_blocked` ahead of `escalated` and `_state`; `_state` keeps its original `ready_commit` signature; JSON field, rendered lines, exit 1.
- `specy_road/bundled_scripts/do_next_prompt.py` — executor hand-off step names the blocked_on stop rule (A2).
- `specy_road/templates/specyrd/commands/specyrd-handoff-status.md` — documents `executor_blocked`.
- `docs/orchestration-review.md` — describes `blocked_on`, its precedence over `blocked`/`escalated`, commit binding, and coordinator resolution.
- `CHANGELOG.md` — Unreleased entry.
- Tests in `tests/test_review_files.py`, `tests/test_review_evidence.py`, `tests/test_mark_implementation_reviewed_gate.py`, `tests/test_review_hardening.py`.

## Verification

```text
pytest tests/test_review_evidence.py tests/test_review_files.py tests/test_mark_implementation_reviewed_gate.py tests/test_review_rca.py tests/test_review_hardening.py::test_scaffold_ships_hand_off_templates_and_the_prompt_names_them -q -p no:cacheprovider
# 67 passed in 64.00s
specy-road file-limits
# OK: file limits satisfied.
```

```text
pytest -q -p no:cacheprovider -x
# 2531 passed, 2 skipped in 805.06s
```

## Touch zones (confirmed)

`specy_road/schemas/handoff.schema.json`, `specy_road/templates/project/work/handoff-ready.template.md`, `specy_road/bundled_scripts/do_next_prompt.py`, `specy_road/review_files.py`, `specy_road/review_gate.py`, `specy_road/bundled_scripts/review_cli.py`, `specy_road/templates/specyrd/commands/specyrd-handoff-status.md`, `docs/orchestration-review.md`, `CHANGELOG.md`, `tests/` — no additions or removals.

## Added

- `ready_semantic_errors` `blocked_on` branch in `review_files.py` — A1: ids must match the brief.
- `executor_blocked_entries`, `executor_blocked_display_lines`, `executor_blocked_gate_problems` in `review_files.py` — A3/A4 shared READY parsing.
- `_node_status` guard in `review_cli.py`: blocked lines only when `same_commit(ready_commit, t.commit)`, and `executor_blocked` chosen before `escalated` / `_state` — A3 precedence (Sol finding 1).
- `_render` / `_EXIT` wiring in `review_cli.py` — A3 handoff status output and exit 1.
- `evaluate_gate` guard in `review_gate.py`: executor-blocked problems added only when the READY commit is the commit under review — A4 without binding later commits (Sol finding 2).
- Executor hand-off paragraph in `_finish_instruction_lines` — A2 prompt rule.
- `test_ready_blocked_on_accepts_known_acceptance_ids`, `test_ready_blocked_on_rejects_unknown_acceptance_id` — A1.
- `test_handoff_status_executor_blocked_lists_entries_and_exits_one`, `test_handoff_status_executor_blocked_json`, `test_executor_blocked_keeps_gate_unmet_even_with_approval` — A3/A4 gate.
- `test_a_stale_blocked_ready_does_not_block_a_later_commit` — gate commit binding (Sol finding 2).
- `test_executor_blocked_outranks_a_reviewer_block_and_escalation` — state collision via public `handoff status` with a recorded block and `escalate_review_rounds: 1` (Sol finding 1).
- `test_yes_refuses_while_ready_declares_blocked_on` — A4 `mark-implementation-reviewed --yes` refusal.
- `test_finish_refuses_while_ready_declares_blocked_on` — A4 refusal through public `finish_task.main` after a real `--yes` approval, READY bound to the reviewed commit (Sol finding 3).
- `_blocked_on_ready(repo, commit=None)` test fixture — writes a `blocked_on` READY; optional `commit` because the approval commit is bookkeeping and the reviewed commit stays the implementation commit.
- `BLOCKED_ON`, `_ready_blocked` fixtures in `test_review_evidence.py` — shared blocked READY text.
- Assert on `blocked_on` in `test_scaffold_ships_hand_off_templates_and_the_prompt_names_them` — A2 smoke.
- Mocks: none.
