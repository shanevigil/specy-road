# Implementation summary: M22.33 — A resumed review runs on the model it was asked for

Branch `feature/rm-reviewer-resume-keeps-the-model`. Fix commit `bdcf765c`, on top of WIP `dbf7129c`, merged in to pick up the added touch zone.

## What changed

- `specy_road/worker_adapter_codex.py`: when `Codex.reviewer_launch` resumes a session (`session=(id, True)`), it now passes `*_model_flag("-m", model)`. The fresh reviewer turn and the worker resume already do this. Before the fix, a format-repair retry ran on Codex's configured default model, but its verdict was filed under the requested id. The docstring now says so.
- `tests/test_review_record_write.py`: `test_codex_reviewer_runs_read_only_with_the_output_schema` checked the exact resumed argv without `-m`. It now expects `"-m", "gpt-6.1-sol"` after `"--json"`. This is the zone the user added. The test still checks the full argv, so it is no weaker.
- `tests/test_harness_launch.py`: added a new test, parametrized over the three adapters (A1, A2).
- `CHANGELOG.md`: added an `[Unreleased]` / `### Fixed` entry.

## Acceptance

- **A1:** Codex's `exec resume` for a reviewer now carries the same `-m` as the fresh turn.
  - Claude Code was already correct. `ClaudeCode.reviewer_launch` builds one argv for fresh and resumed turns, and it includes `--model` (`specy_road/worker_adapter_claude.py:92-93`).
  - Cursor was already correct (`specy_road/worker_adapter_cursor.py:229-231`).
  - The new test confirms all three. Neither Claude Code nor Cursor needed a change.
- **A2:** `test_a_reviewer_resume_passes_the_requested_model[claude-code|codex|cursor]` checks two things for each adapter:
  - **Direct resume:** the adapter's reviewer resume argv names the session and has the model flag with the requested model.
  - **Repair path:** it runs the format-repair retry through `review_delegate.delegate`. A clean turn with an empty final message triggers the one repair turn. The test checks that the attempts are `[fresh, repair]`, that the repair launch resumes the reported session, and that the fresh and repair launches carry the same model.

## Verification

- Red-green: with the Codex change reverted, `tests/test_harness_launch.py::test_a_reviewer_resume_passes_the_requested_model` fails for `codex--m` with `ValueError` (no `-m` in the argv). With the fix, all three cases pass.
- `pytest -n 4 tests/test_harness_launch.py tests/test_review_record_write.py tests/test_review_record_write_closure.py tests/test_worker_adapters.py tests/test_review_delegate.py tests/test_headless_limits_denials.py tests/test_worker_turn_check.py`: 137 passed.
- Full suite `pytest -n 4`: 5959 passed.
- `specy-road file-limits`: OK. The two warnings it prints are on files this leaf did not touch.

## Final touch zones

`specy_road/worker_adapter_codex.py`, `tests/test_harness_launch.py`, `tests/test_review_record_write.py`, `CHANGELOG.md`. `specy_road/worker_adapter_claude.py` is still zoned, but it needed no change.

## Added

- Branch: `Codex.reviewer_launch` resume argv now includes `_model_flag("-m", model)`, so a resumed review runs on the requested model (A1).
- Test: `tests/test_harness_launch.py::test_a_reviewer_resume_passes_the_requested_model`, parametrized over claude-code, codex and cursor. It covers each adapter's reviewer resume argv and the format-repair retry through `review delegate` (A2).
- Mock: in that test, `review_delegate.delegate_turn` is monkeypatched to return a clean turn with a session id and no answer. This triggers the repair turn without a real harness, and the stub records each launch. The same public patch point is used by `test_worker_and_reviewer_launches_run_the_resolved_binary`.
- Helpers, guards: none.
