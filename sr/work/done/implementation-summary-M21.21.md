# Implementation summary: M21.21 — review delegate validates the reviewer command

Branch `feature/rm-review-delegate-validates-reviewer-command`, base `840b76b6`. Fix commit `15f392ab`; fix round 1:
merge of `origin/WIP/improvements-0-3-1` (`56568a43`), then `0f44b76a`.

## What changed

- `specy_road/review_delegate_harness.py` (`_Harness.__init__`): a non-chore reviewer is now checked by
  `role_prompt_cli.reviewer_command`, the same validator `prompt --channel cli` uses, and a refusal raises
  `HarnessSetupError` with its reason. `delegate()` builds `_Harness` before the lock, `_start`, `_preflight` and
  `save_run`, so a refusal starts no process and writes no `RUN-<model>.json` or log, on a fresh run and on
  `--resume` alike. The generic `prof.cli()` (profile `access.cli`) fallback now applies to chore reviewers only.
  A chore reviewer's launch is unchanged.
- Model handling (fix round 1): `reviewer_command` checks the roster entry itself, with no placeholder model. An
  entry that resolves to no API model id is refused with `reviewer_command`'s reason ("resolves to no API model
  id"), whatever its `routing`, before the preflight and before any run file. This is the same check `prompt
  --channel cli` applies. The old "no model would be passed … routing: dynamic" path in `review_delegate.py`
  (outside the zones, unchanged) is now reached only by chore reviewers, whose launch is unchanged. Round 1 had
  substituted `harness_model: '-'` so that path stayed reachable, which let a `routing: dynamic` reviewer launch
  where `prompt` refuses it (gpt-6.1-sol-low's block).
- `specy_road/review_model_check.py` (`reported_models`): a str log is split with `review_answer.stream_lines`
  (`\n` only) instead of `str.splitlines`. This adds no import cycle (`review_answer` does not import
  `review_model_check`).
- `CHANGELOG.md`: two entries under [Unreleased] Fixed.

## Acceptance

- A1: the shared table's delegate rows, and the chore test (the same `--force` roster entry is refused for leaf
  M1.1 and launches for chore `fix-env`). `test_refusals` now expects the generic no-cli refusal for `plain`. Its
  "unsupported by generic: resume" check still runs, on a generic entry that has a clean `channels.cli`.
- A2: `test_every_reviewer_entry_point_refuses_the_same_reviewer_command`, 6 rows × {prompt, delegate,
  delegate --resume}. The rows are the 4 command rows plus 2 no-model rows (profile `api_id: unknown`, with and
  without `routing: dynamic`). Each row checks the same reason text, that no non-git process started (the `started` Popen
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

## Fix round 1

- Finding class: "delegate validates something other than the roster entry it will launch". The one instance was
  the placeholder `harness_model` that hid `model_problem`. The fix removes the substitution, so the delegate now
  runs the same `reviewer_command(prof, entry, …)` call `prompt` does, with no branch around it.
- Tests: the old `test_delegate_refuses_when_no_model_would_be_passed_and_opens_no_run_record` and
  `test_delegate_launches_when_routing_dynamic_accepts_the_harness_default` (with their `_unknown_api_delegate_repo`
  helper) were removed from `tests/test_review_delegate.py`. The reviewer's required change says the second one's
  expectation conflicts with A1. The first one's case (no model, no launch, no RUN record) is now the shared
  table's no-model rows, which assert the same reason on all three entry points, no process, no preflight, and RUN
  files unchanged. The unused `FAKE` and profile imports went with them.
- The chore test moved back to `tests/test_review_delegate.py`, which now has room for it.
- Red/green: with round 1's harness restored, the 4 delegate and delegate --resume no-model rows fail and the rest
  pass.

## Probes

- `routing: dynamic` + profile `api_id: unknown` on delegate and delegate --resume: refused with "resolves to no API
  model id", no process, no preflight, RUN files unchanged (table rows)
- Same without `routing`: refused with the same reason before preflight. Before this round it was refused after the
  preflight with a different reason (table rows)
- `prompt --channel cli --run` on both no-model rows: refused, as before (table rows; existing
  `test_a_model_with_no_api_id_is_refused_before_launch_on_every_command` still passes)
- `review delegate --resume`: builds the same `_Harness`, so no separate resume-only path skips the check (resume
  table rows)
- Chore reviewer path (`chore=True`): not validated, and it keeps the `prof.cli()` fallback and the later no-model
  check (`test_a_chore_reviewer_keeps_its_launch_that_a_leaf_reviewer_is_refused`; `tests/test_chore_mode.py`
  passes)
- Remaining reader of `routing: dynamic` for a non-chore reviewer in `review_delegate.py:207`: now unreachable for
  non-chore entries, still used for chores. It is outside the zones and left unchanged
- `docs/` promising that a dynamic reviewer launches: none found (`grep dynamic docs/*.md`)
- Other substitutes of the entry before validation in the zoned files: none (`reviewer_command` is called once, with
  `entry`)

## Touch zones (final)

The list is unchanged: `specy_road/review_delegate_harness.py`, `specy_road/review_model_check.py`,
`tests/test_review_delegate.py`, `tests/test_prompt_channel_cli_run.py`, `CHANGELOG.md`. In round 1 the chore test
sat in `tests/test_prompt_channel_cli_run.py`, because `tests/test_review_delegate.py` would have gone over the
400-line limit. Since fix round 1 it is back in `tests/test_review_delegate.py` (372 lines). No new module was
needed.

## Verification

- Round 1: `python -m pytest -q -n 4 tests/test_review_delegate.py tests/test_prompt_channel_cli_run.py
  tests/test_effective_model.py tests/test_chore_mode.py`: 122 passed
- Round 1: `python -m pytest -q -n 4` (after the merge): 5464 passed and 1 failed,
  `tests/test_review_usage.py::test_delegate_after_prompt_cli_does_not_append_to_the_old_log`. That test passes
  alone and in 3 parallel reruns of its file, so this looks like a load flake; I did not establish the cause.
- `ruff check specy_road tests scripts` and `specy-road file-limits`: clean
- `specy-road file-limits`: OK; `ruff check` on the touched files: clean

## Added

- guard: `_Harness.__init__` calls `reviewer_command` for non-chore reviewers and raises `HarnessSetupError`. This is
  the fix for W1.
- branch: the `prof.cli()` fallback is limited to `chore=True`, to keep the chore reviewer's launch unchanged.
- change: `reported_models` uses `stream_lines`. This is the fix for W2.
- test: `REFUSED_REVIEWERS` (with an `api_id` column and the `NO_MODEL` reason) +
  `test_every_reviewer_entry_point_refuses_the_same_reviewer_command` (A1/A2 shared table, including no-model with
  and without `routing: dynamic`).
- removed: the placeholder `harness_model` branch from round 1, and the two superseded no-model delegate tests and
  their helper (see Fix round 1).
- test: `test_a_chore_reviewer_keeps_its_launch_that_a_leaf_reviewer_is_refused` (A1: the chore launch is
  unchanged).
- test rows: the U+2028 row in `test_check_run_flags_any_reported_model_that_is_not_the_rostered_one` and in
  `test_a_mismatched_model_is_filed_flagged_and_excluded_from_the_gate` (A3).
- test change: `test_refusals` expects the new generic refusal and keeps the resume-unsupported check on a generic
  entry with a clean cli.
- mocks: none new. The existing `started` Popen recorder and the fake harness scripts are reused.
