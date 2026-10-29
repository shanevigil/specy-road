# Implementation summary — M3.18

## Goal

Bring `role_prompt.py` and `review_gate.py` under the 400-line file cap and clear ruff C901 on stale-command mention scanning, with no behaviour change. Full `file-limits` and `ruff check specy_road tests` must pass.

## Touch zones (confirmed)

- `specy_road/bundled_scripts/role_prompt.py`
- `specy_road/bundled_scripts/role_prompt_rca.py` (new)
- `specy_road/bundled_scripts/validate_stale_commands.py`
- `specy_road/bundled_scripts/validate_stale_mentions.py` — removed in round 1 (circular import)
- `specy_road/review_gate.py`
- `specy_road/review_gate_ready.py` (new)
- `docs/orchestration.md`
- `docs/orchestration-review.md` (new)
- `specy_road/bundled_scripts/brainstorm_cli.py`
- `specy_road/bundled_scripts/brainstorm_cli_revise.py` (new)
- `tests/` — unchanged; existing tests cover behaviour

## Changes

**A1 — file cap:** Moved prompt builders into `role_prompt_rca.py` (`role_prompt.py` 201 lines). After M3.17, moved `write_human_approval` and trial-merge helpers into `review_gate_ready.py` (`review_gate.py` 335 lines; one-way re-export).

**Round 3:** Moved the whole "The review gate" section (counting rules, signed reviews, `handoff status`, escalation) from `docs/orchestration.md` into `docs/orchestration-review.md` and linked it from the quickstart and a stub heading. `docs/orchestration.md` is 325 lines.

**A2 — C901:** Split `_command_mentions` into `_mentions_in_fenced_line` and `_mentions_on_open_line` in `validate_stale_commands.py`.

**Round 3:** Moved `cmd_revise` and `_revise_content` / `_revise_why` / `_revise_links` / `_apply_revise` into `brainstorm_cli_revise.py`. `brainstorm_cli` imports `cmd_revise` one way.

**Round 1 (block):** Removed the `validate_stale_mentions` circular import.

## Verification

- `specy-road file-limits` — exit 0 (`OK: file limits satisfied.`)
- `ruff check specy_road tests` — exit 0 (`All checks passed!`)
- pytest of docs, brainstorm, prompt, and review modules — 130 passed

## Added

- `role_prompt_rca.py` — moved preamble builders; reason: file cap on `role_prompt.py`.
- `_mentions_in_fenced_line` / `_mentions_on_open_line` — reason: C901 on `_command_mentions`.
- `review_gate_ready.py` — moved `write_human_approval` and trial-merge helpers; reason: file cap on `review_gate.py`.
- `docs/orchestration-review.md` — moved the review-gate section; reason: file cap on `docs/orchestration.md`.
- `brainstorm_cli_revise.py` — moved `cmd_revise` and its helpers; reason: C901 on `cmd_revise`.

## Removed (round 1)

- `validate_stale_mentions.py` — circular import.
- trailing `# noqa: E402` import of `_command_mentions`.

## Helpers, branches/guards, mocks, tests

- helpers: as above
- branches or guards: none
- mocks: none
- tests: none
