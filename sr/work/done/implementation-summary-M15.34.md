# Implementation summary: M15.34

## Goal

State the three lean test rules in the executor prompt and build the reviewer's two test-related excess-checklist bullets from the same `TEST_RULES` strings so executor and reviewer guidance cannot drift.

## Touch zones (confirmed)

- `specy_road/bundled_scripts/role_prompt_rca.py` — `TEST_RULES`, `executor_preamble`, `_EXCESS_CHECKLIST`
- `tests/` — `tests/test_lean_rules.py` only

No other paths were required.

## Acceptance

- **A1:** `TEST_RULES` holds three sentences; `executor_preamble` adds a `**Tests:**` block after step 3; `_EXCESS_CHECKLIST` test bullets quote `TEST_RULES[0]`/`[2]` and `TEST_RULES[1]`.
- **A2:** `test_executor_and_reviewer_prompts_share_test_rules` builds both prompts via `role_prompt.build_prompt` and asserts every `TEST_RULES` sentence appears in each (rework prompts reuse `executor_preamble`, so they inherit the block).

## Verification

- `pytest tests/test_lean_rules.py -q`
- `specy-road file-limits`

## Added

- `TEST_RULES` tuple in `role_prompt_rca.py` — single source for the three test sentences (A1).
- `**Tests:**` block in `executor_preamble` after step 3 — surfaces rules to executors (A1).
- `_EXCESS_CHECKLIST` f-strings for *Test pins internals* and *Overlapping test* — reuse `TEST_RULES` instead of paraphrasing (A1).
- `test_executor_and_reviewer_prompts_share_test_rules` in `tests/test_lean_rules.py` — regression that both prompts contain every rule (A2).
