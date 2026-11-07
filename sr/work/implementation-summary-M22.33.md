# Implementation summary: M22.33 — A resumed review runs on the model it was asked for

Branch `feature/rm-reviewer-resume-keeps-the-model`. Fix commit `bdcf765c`, on top of WIP `dbf7129c`, merged in to pick up the added touch zone. Rework commit `3aee8bc0` answers the `gpt-5.6-sol-high` block on `ed2def67`.

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
  - **Repair path:** it runs the format-repair retry through `review_delegate.delegate` against a fake reviewer harness, `FAKE_REVIEWER`, set as the roster entry's `harness_bin`. The fake records each argv it is started with and ends a clean turn with an empty final message, in that harness's stream format. That triggers the one repair turn. The test checks three things:
    - the attempts are `[fresh, repair]`;
    - the repair launch resumes the session the run recorded;
    - the fresh and repair launches carry the same model.

    It picks each launch from the recorded argvs by whether it resumes (`--resume`, or `exec resume` on Codex), not by call order. Nothing in specy-road is stubbed.

## Rework (block by `gpt-5.6-sol-high` on `ed2def67`)

The finding's class is a test that observes a launch through an internal seam and by position. The test read the repair argv from a positional `seen` list filled by a `delegate_turn` stub, so a rewrite that kept the behaviour could still break it on call shape. The fix removes the seam from this test. A real `delegate` runs a fake harness process, and the test selects launches from that process's recorded argv by flag.

## Probes

- The M22.33 test's repair path: it no longer patches `delegate_turn` and no longer reads launches by index. It now runs a real fake process and selects launches by flag. Result: fixed.
- The direct resume argv check in the same test: it calls the public `reviewer_launch` and reads the flag's value, not its position. Result: no seam.
- `tests/test_review_record_write.py`, the edited resume argv: it compares the exact argv returned by public `Codex.reviewer_launch`. It has no mock and no call count. Result: no seam.
- Private names in this change: the test imports no `_`-prefixed product name. `_exe` and `_resumes` are helpers local to the test file. Result: clean.
- Other `delegate_turn` stubs in `tests/test_harness_launch.py` (`test_worker_and_reviewer_launches_run_the_resolved_binary`, `test_a_missing_binary_refuses_every_launch_before_anything_runs`): they predate this leaf and the change does not touch them. Result: left as they are, out of scope.
- The fake-harness path catches the regression without the direct check. With the Codex fix reverted and the direct argv assertion removed for the probe, the `codex--m` case fails at the repair argv check (`'-m' is not in list`). The other two cases pass. Result: confirmed, then restored.

## Verification

- Red-green: with the Codex change reverted, `tests/test_harness_launch.py::test_a_reviewer_resume_passes_the_requested_model` fails for `codex--m` with `ValueError` (no `-m` in the argv). With the fix, all three cases pass.
- `pytest -n 4 tests/test_harness_launch.py tests/test_review_record_write.py tests/test_review_record_write_closure.py tests/test_worker_adapters.py tests/test_review_delegate.py tests/test_review_delegate_repair.py tests/test_headless_limits_denials.py tests/test_worker_turn_check.py`: 165 passed.
- Full suite `pytest -n 4`: 5959 passed, after the rework.
- `specy-road file-limits`: OK. The two warnings it prints are on files this leaf did not touch.

## Final touch zones

`specy_road/worker_adapter_codex.py`, `tests/test_harness_launch.py`, `tests/test_review_record_write.py`, `CHANGELOG.md`. `specy_road/worker_adapter_claude.py` is still zoned, but it needed no change.

## Added

- Branch: `Codex.reviewer_launch` resume argv now includes `_model_flag("-m", model)`, so a resumed review runs on the requested model (A1).
- Test: `tests/test_harness_launch.py::test_a_reviewer_resume_passes_the_requested_model`, parametrized over claude-code, codex and cursor. It covers each adapter's reviewer resume argv and the format-repair retry through `review delegate` (A2).
- Fake: `FAKE_REVIEWER` in `tests/test_harness_launch.py`, a script set as the roster entry's `harness_bin`. It records its argv and ends a clean turn with an empty final message in the harness's stream format. This drives the real repair path without a real harness. It replaces the earlier `delegate_turn` stub (rework).
- Helper: `_resumes` in that test file. It tells a resume launch from a fresh one by flag (`--resume` or `exec resume`), so launches are selected by what they are, not by order (rework).
- Mocks: none.
- Helpers, guards: none.
