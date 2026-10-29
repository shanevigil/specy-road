# Implementation summary — M3.18

## Goal

Bring `role_prompt.py` under the 400-line file cap and clear ruff C901 on stale-command mention scanning, with no behaviour change.

## Touch zones (confirmed)

- `specy_road/bundled_scripts/role_prompt.py`
- `specy_road/bundled_scripts/role_prompt_rca.py` (new)
- `specy_road/bundled_scripts/validate_stale_commands.py`
- `specy_road/bundled_scripts/validate_stale_mentions.py` — removed in round 1 (circular import)
- `tests/` — unchanged; existing tests cover behaviour

## Changes

**A1 — file cap:** Moved precondition, role preamble, and model profile section builders from `role_prompt.py` into new `role_prompt_rca.py`. `role_prompt.build_prompt` imports and calls the same logic via public names (`precondition`, `executor_preamble`, etc.). `role_prompt.py` is 201 lines; `specy-road file-limits` passes.

**A2 — C901:** Split `_command_mentions` into `_mentions_in_fenced_line` and `_mentions_on_open_line` in `validate_stale_commands.py` so complexity stays under the limit. Scan control flow is unchanged.

**Round 1 (block):** Removed the import cycle. `validate_stale_mentions.py` is gone; the fence helpers and `_command_mentions` live in `validate_stale_commands.py` only. No `# noqa: E402` import remains.

## Verification

- `specy-road file-limits` — exit 0 (`OK: file limits satisfied.`)
- `ruff check specy_road tests` — exit 0 (`All checks passed!`)
- `pytest tests/test_validate_stale_commands.py tests/test_models_and_prompt.py tests/test_review_rca.py tests/test_lean_rules.py` — 46 passed
- `python -c 'import specy_road.bundled_scripts.validate_stale_commands'` — succeeds without a trailing import

## Added

- `role_prompt_rca.py` — houses moved preamble/precondition/profile builders; reason: file cap on `role_prompt.py`.
- `_mentions_in_fenced_line` / `_mentions_on_open_line` in `validate_stale_commands.py` — reason: reduce cyclomatic complexity of `_command_mentions` without changing scan results.

## Removed (round 1)

- `validate_stale_mentions.py` — reason: it imported `_MENTION`/`_code_spans`/`_reports`/`_span_command_token` from `validate_stale_commands`, which then imported `_command_mentions` back; importing the new module first raised ImportError.
- trailing `# noqa: E402` import of `_command_mentions` — reason: no longer needed once helpers live in one module.

## Helpers, branches/guards, mocks, tests

- helpers: as above
- branches or guards: none
- mocks: none
- tests: none
