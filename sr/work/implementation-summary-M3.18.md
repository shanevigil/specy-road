# Implementation summary — M3.18

## Goal

Bring `role_prompt.py` and `review_gate.py` under the 400-line file cap and clear ruff C901 on stale-command mention scanning, with no behaviour change. Full `file-limits` and `ruff check specy_road tests` must pass.

## Touch zones (confirmed)

- `specy_road/bundled_scripts/role_prompt.py`
- `specy_road/bundled_scripts/role_prompt_rca.py` (new)
- `specy_road/bundled_scripts/validate_stale_commands.py`
- `specy_road/bundled_scripts/validate_stale_mentions.py` — removed in round 1 (circular import)
- `specy_road/review_gate.py` — added after M3.17 landed (A1 widened)
- `specy_road/review_gate_ready.py` (new)
- `docs/orchestration.md` — round 2 (Sol): full file-limits gate
- `specy_road/bundled_scripts/brainstorm_cli.py` — round 2 (Sol): full ruff C901 gate
- `tests/` — unchanged; existing tests cover behaviour

## Changes

**A1 — file cap:** Moved precondition, role preamble, and model profile section builders from `role_prompt.py` into new `role_prompt_rca.py`. `role_prompt.py` is 201 lines.

After merging `origin/WIP/improvements-0-3-1` (M3.17 pushed `review_gate.py` to 420 lines), moved `write_human_approval` and the trial-merge helpers (`TRIAL_MERGE_BOOKKEEPING`, `is_trial_merge_bookkeeping`, `TrialMerge`, `trial_merge`, `trial_merge_or_exit`) into new `review_gate_ready.py`. `review_gate.py` re-exports those names (one-way import; `review_gate_ready` does not import `review_gate`). `review_gate.py` is 335 lines.

**Round 2 (Sol block):** Joined the Coordinator and Executor wrap lines in `docs/orchestration.md` (402 → 400). No wording change.

**A2 — C901:** Split `_command_mentions` into `_mentions_in_fenced_line` and `_mentions_on_open_line` in `validate_stale_commands.py` so complexity stays under the limit. Scan control flow is unchanged.

**Round 2 (Sol block):** Moved `cmd_revise` body into `_revise_content`, `_revise_why`, `_revise_links`, and `_apply_revise` so C901 is under 10. Control flow is unchanged.

**Round 1 (block):** Removed the import cycle. `validate_stale_mentions.py` is gone; the fence helpers and `_command_mentions` live in `validate_stale_commands.py` only. No `# noqa: E402` import remains.

## Verification

- `specy-road file-limits` — exit 0 (`OK: file limits satisfied.`)
- `ruff check specy_road tests` — exit 0 (`All checks passed!`)
- `pytest` brainstorm revise modules — 70 passed
- `python -c 'import specy_road.review_gate_ready'` then `review_gate` — both import cleanly

## Added

- `role_prompt_rca.py` — moved preamble/precondition/profile builders; reason: file cap on `role_prompt.py`.
- `_mentions_in_fenced_line` / `_mentions_on_open_line` in `validate_stale_commands.py` — reason: C901 on `_command_mentions`.
- `review_gate_ready.py` — moved `write_human_approval` and trial-merge helpers; reason: file cap on `review_gate.py` after M3.17.
- `_revise_content` / `_revise_why` / `_revise_links` / `_apply_revise` in `brainstorm_cli.py` — reason: C901 on `cmd_revise` for the full ruff gate.

## Removed (round 1)

- `validate_stale_mentions.py` — reason: circular import with `validate_stale_commands`.
- trailing `# noqa: E402` import of `_command_mentions` — reason: no longer needed.

## Helpers, branches/guards, mocks, tests

- helpers: as above
- branches or guards: none
- mocks: none
- tests: none
