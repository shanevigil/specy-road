## Summary

Leaf M9.4 adds an optional `blocked_on` list to READY hand-offs so executors can stop when an acceptance criterion would require weakening tests or raising baselines/caps, without bypassing the review gate. Schema validation, semantic checks against brief acceptance ids, handoff status (`executor_blocked`), and gate refusal are wired through the existing review pipeline.

## Changes

- `specy_road/schemas/handoff.schema.json` — optional `blocked_on` array with `acceptance` (`A<n>`) and non-empty `reason`.
- `specy_road/templates/project/work/handoff-ready.template.md` — commented example for `blocked_on`.
- `specy_road/review_files.py` — `ready_semantic_errors` validates acceptance ids; helpers for gate and handoff display.
- `specy_road/review_gate.py` — `evaluate_gate` appends `executor_blocked_gate_problems`.
- `specy_road/bundled_scripts/review_cli.py` — `executor_blocked` state, JSON field, rendered lines, exit 1.
- `specy_road/bundled_scripts/do_next_prompt.py` — executor hand-off step names the blocked_on stop rule (A2).
- `specy_road/templates/specyrd/commands/specyrd-handoff-status.md` — documents `executor_blocked`.
- `docs/orchestration-review.md` — describes `blocked_on` and coordinator resolution.
- `CHANGELOG.md` — Unreleased entry.
- Tests in `tests/test_review_files.py`, `tests/test_review_evidence.py`, `tests/test_mark_implementation_reviewed_gate.py`, `tests/test_review_hardening.py`.

## Verification

```text
pytest tests/test_review_evidence.py tests/test_review_files.py tests/test_mark_implementation_reviewed_gate.py tests/test_review_hardening.py::test_scaffold_ships_hand_off_templates_and_the_prompt_names_them -q
# 55 passed
```

## Touch zones (confirmed)

`specy_road/schemas/handoff.schema.json`, `specy_road/templates/project/work/handoff-ready.template.md`, `specy_road/bundled_scripts/do_next_prompt.py`, `specy_road/review_files.py`, `specy_road/review_gate.py`, `specy_road/bundled_scripts/review_cli.py`, `specy_road/templates/specyrd/commands/specyrd-handoff-status.md`, `docs/orchestration-review.md`, `CHANGELOG.md`, `tests/` — no additions or removals.

## Added

- `ready_semantic_errors` `blocked_on` branch in `review_files.py` — A1: ids must match the brief.
- `executor_blocked_entries`, `executor_blocked_display_lines`, `executor_blocked_gate_problems` in `review_files.py` — A3/A4 shared READY parsing.
- `_state` / `_node_status` / `_render` / `_EXIT` wiring in `review_cli.py` — A3 handoff status.
- `evaluate_gate` verifier_problems extension in `review_gate.py` — A4 gate unmet while blocked.
- Executor hand-off paragraph in `_finish_instruction_lines` — A2 prompt rule.
- `test_ready_blocked_on_accepts_known_acceptance_ids`, `test_ready_blocked_on_rejects_unknown_acceptance_id` — A1.
- `test_handoff_status_executor_blocked_*`, `test_executor_blocked_keeps_gate_unmet_even_with_approval` — A3/A4 gate.
- `test_yes_refuses_while_ready_declares_blocked_on`, `test_finish_refuses_while_ready_declares_blocked_on`, `_blocked_on_ready` — A4 CLI refusal.
- Assert on `blocked_on` in `test_scaffold_ships_hand_off_templates_and_the_prompt_names_them` — A2 smoke.
