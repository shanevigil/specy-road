# Implementation summary — M3.18

## Goal

Bring `role_prompt.py` under the 400-line file cap and clear ruff C901 on stale-command mention scanning, with no behaviour change.

## Touch zones (confirmed)

- `specy_road/bundled_scripts/role_prompt.py`
- `specy_road/bundled_scripts/role_prompt_rca.py` (new)
- `specy_road/bundled_scripts/validate_stale_commands.py`
- `specy_road/bundled_scripts/validate_stale_mentions.py` (new)
- `tests/` — unchanged; existing tests cover behaviour

## Changes

**A1 — file cap:** Moved precondition, role preamble, and model profile section builders from `role_prompt.py` into new `role_prompt_rca.py`. `role_prompt.build_prompt` imports and calls the same logic via public names (`precondition`, `executor_preamble`, etc.). `role_prompt.py` is 201 lines; `specy-road file-limits` passes.

**A2 — C901:** Split `_command_mentions` into `validate_stale_mentions.py` with `_mentions_in_fenced_line` and `_mentions_on_open_line` helpers so complexity stays under the limit. `validate_stale_commands` re-imports `_command_mentions` at module end (after `_occurrences` is defined) to avoid import cycles while keeping the same public module API.

## Verification

- `specy-road file-limits` — exit 0 (`OK: file limits satisfied.`)
- `ruff check specy_road tests` — exit 0 (`All checks passed!`)
- `pytest tests/test_validate_stale_commands.py tests/test_models_and_prompt.py tests/test_review_rca.py tests/test_lean_rules.py` — 46 passed

## Added

- `role_prompt_rca.py` — houses moved preamble/precondition/profile builders; reason: file cap on `role_prompt.py`.
- `validate_stale_mentions.py` — fence-aware mention iteration split from `_command_mentions`; reason: ruff C901 on `validate_stale_commands._command_mentions`.
- `_mentions_in_fenced_line` / `_mentions_on_open_line` in `validate_stale_mentions.py` — reason: reduce cyclomatic complexity of `_command_mentions` without changing scan results.
- E402 import of `_command_mentions` at end of `validate_stale_commands.py` — reason: break circular import while preserving `validate_stale_commands._command_mentions` for callers.
- none — tests, mocks, or new guards.
