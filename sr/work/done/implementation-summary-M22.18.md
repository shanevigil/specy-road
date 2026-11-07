# Implementation summary: M22.18 — the reviewer prompt asks for every required change in one pass

Branch `feature/rm-reviewer-lists-every-required-change`, base `b6f37eecc5287e1b052ba443d4fce85ca81b1a28`.

## What changed

- **A1.** `schema_lines()` in `specy_road/review_record_write.py` now tells the reviewer, in the section every reviewer prompt already appends, to list every required change it can find in this one review, re-scan the diff for further instances of each defect class (other inputs, other call sites, other files) and any acceptance line not fully met before answering, and that a later round should find nothing it could have reported now. `review delegate` and `prompt --role reviewer` (`--channel cli` and `paste`) all render that section. `build_prompt` is unchanged.
- **A2.** `tests/test_role_prompt_reviewer.py` renders the reviewer prompt for `delegate`, `cli` and `paste` and asserts that instruction is present once, and that the same text is in `schema_lines()`. No prompt byte-budget test exists, so none was resized. `specy-road file-limits` passes; `build_prompt` gained no line.
- **A3.** `docs/orchestration-reviewer-output.md` states the expectation. `CHANGELOG.md` `[Unreleased]` / `### Changed` records it.

## Touch zones

Declared: `specy_road/bundled_scripts/role_prompt.py`, `specy_road/review_record_write.py`, `tests/test_role_prompt_reviewer.py`, `docs/orchestration-reviewer-output.md`, `CHANGELOG.md`.

`role_prompt.py` stays unchanged: `build_prompt` already appends `schema_lines()` for a reviewer, and the plan keeps that function free of new lines. No path outside the declared zones needed a change. The roadmap zone list was not edited.

## Verification

- `pytest -n 4 tests/test_role_prompt_reviewer.py tests/test_role_prompt_file_limits.py tests/test_review_record_write.py`: 44 passed.
- `specy-road file-limits`: OK (existing hard-alert warnings only).

## Added

### Helpers

- none

### Branches or guards

- none

### Mocks

- none

### Tests

- `test_every_reviewer_channel_lists_every_required_change_once` — one parametrized case per channel (`delegate`, `cli`, `paste`) so each rendered reviewer prompt contains the `schema_lines()` instruction once.
