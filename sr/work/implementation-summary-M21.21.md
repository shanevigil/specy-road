# Implementation summary: M21.21 — review delegate validates the reviewer command

Branch `feature/rm-review-delegate-validates-reviewer-command`, base `840b76b6`. Fix commit `15f392ab`.

## What changed

- `specy_road/review_delegate_harness.py` (`_Harness.__init__`): a non-chore reviewer is now checked by
  `role_prompt_cli.reviewer_command`, the same validator `prompt --channel cli` uses, and a refusal raises
  `HarnessSetupError` with its reason. `delegate()` builds `_Harness` before the lock, `_start`, `_preflight` and
  `save_run`, so a refusal starts no process and writes no `RUN-<model>.json` or log, on a fresh run and on
  `--resume` alike. The generic `prof.cli()` (profile `access.cli`) fallback now applies to chore reviewers only.
  A chore reviewer's launch is unchanged.
- Model handling: when the entry resolves to no model (`self.api_id is None`), the validator is called with a
  placeholder `harness_model`. This skips only `model_problem` and still applies the cli and bypass checks. The
  existing "no model would be passed … routing: dynamic" refusal in `_delegate_locked` and the dynamic-routing launch
  keep their behaviour; the tests for both still pass unchanged. An explicit `harness_model: unknown` is now refused
  here, as `prompt` refuses it.
- `specy_road/review_model_check.py` (`reported_models`): a str log is split with `review_answer.stream_lines`
  (`\n` only) instead of `str.splitlines`. This adds no import cycle (`review_answer` does not import
  `review_model_check`).
- `CHANGELOG.md`: two entries under [Unreleased] Fixed.

## Acceptance

- A1: the shared table's delegate rows, and the chore test (the same `--force` roster entry is refused for leaf
  M1.1 and launches for chore `fix-env`). `test_refusals` now expects the generic no-cli refusal for `plain`. Its
  "unsupported by generic: resume" check still runs, on a generic entry that has a clean `channels.cli`.
- A2: `test_every_reviewer_entry_point_refuses_the_same_reviewer_command`, 4 rows × {prompt, delegate,
  delegate --resume}. Each row checks the same reason text, that no non-git process started (the `started` Popen
  recorder), that the preflight did not run, and that the RUN-* files are unchanged: none on a fresh run, the seeded
  RUN json and log bytes on a resume. A clean custom command still launches: the existing
  `test_success_builds_the_prompt_launches_and_records_the_session` (claude-code entry with a custom
  `channels.cli`) passes.
- A3: a new `check_run` row (str log with U+2028 inside a JSON string → mismatch) and a new row in
  `test_a_mismatched_model_is_filed_flagged_and_excluded_from_the_gate` (the filed record has `model_mismatch`
  and is excluded from the gate).
- A4: CHANGELOG done. Out-of-scope items not touched.
- A5: package +10/−4 lines, tests about +67.

Red/green: with the package changes stashed, 12 of the new or changed tests fail. These are every delegate row
of the table, both U+2028 rows, the chore test and `test_refusals`. The prompt rows pass before the fix too, as
expected. All pass with the fix.

## Touch zones (final)

The list is unchanged: `specy_road/review_delegate_harness.py`, `specy_road/review_model_check.py`,
`tests/test_review_delegate.py`, `tests/test_prompt_channel_cli_run.py`, `CHANGELOG.md`. The chore test is in
`tests/test_prompt_channel_cli_run.py` rather than `tests/test_review_delegate.py`, because the latter would have
gone over the 400-line file limit (407). No new module was needed.

## Verification

- `python -m pytest -q -n 4 tests/test_review_delegate.py tests/test_prompt_channel_cli_run.py`: 86 passed
- `python -m pytest -q -n 4`: 5434 passed
- `specy-road file-limits`: OK; `ruff check` on the touched files: clean

## Added

- guard: `_Harness.__init__` calls `reviewer_command` for non-chore reviewers and raises `HarnessSetupError`. This is
  the fix for W1.
- branch: placeholder `harness_model` when `api_id is None`, so the later no-model / `routing: dynamic` handling keeps
  its existing reason and behaviour.
- branch: the `prof.cli()` fallback is limited to `chore=True`, to keep the chore reviewer's launch unchanged.
- change: `reported_models` uses `stream_lines`. This is the fix for W2.
- test: `REFUSED_REVIEWERS` + `test_every_reviewer_entry_point_refuses_the_same_reviewer_command` (A1/A2 shared
  table).
- test: `test_a_chore_reviewer_keeps_its_launch_that_a_leaf_reviewer_is_refused` (A1: the chore launch is
  unchanged).
- test rows: the U+2028 row in `test_check_run_flags_any_reported_model_that_is_not_the_rostered_one` and in
  `test_a_mismatched_model_is_filed_flagged_and_excluded_from_the_gate` (A3).
- test change: `test_refusals` expects the new generic refusal and keeps the resume-unsupported check on a generic
  entry with a clean cli.
- mocks: none new. The existing `started` Popen recorder and the fake harness scripts are reused.
