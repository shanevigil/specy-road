# Implementation summary: M11.77 — A completed reviewer run does not report a missing record

## Cause

`close_reviewer_cli_run` (the `prompt --role reviewer --channel cli` path) built the run's
attempt entry with `harness_error_line(exit_code=0, errors=[], …, fallback="")`. That call
returns `"no review record was filed"` on every clean exit, and it ran before the record was
checked, so every completed prompt-cli run had that error in `attempts[0].error` in
`RUN-<model>.json`, even with `state: complete`.

`review delegate` (`review_delegate.py`) was not affected. Its attempt error comes from
harness error events, and `close_run` calls `harness_error_line` only after `valid_record`
fails, always with a non-empty fallback, so the message is never produced there. The new test
pins this down.

## Change

- `specy_road/reviewer_run_failure.py` (`close_reviewer_cli_run`): a clean exit (`exit 0`)
  with a valid `REVIEW-<model>.md` for the commit under review (`valid_record`) now records
  `error: None` on the attempt. Without such a record, the attempt still says
  `no review record was filed`. A non-zero exit keeps its harness error line as before.
  `state`, `reason` and the reviewer-failure event are still set by `close_run`, unchanged.

## Touch zones (final)

- `specy_road/reviewer_run_failure.py`: changed
- `specy_road/review_delegate.py`: unchanged (already correct; covered by a test)
- `tests/`: new `tests/test_run_record_no_false_failure.py`

Call sites outside the zones (`bundled_scripts/role_prompt.py`, `bundled_scripts/review_cli.py`)
needed no change: the signatures did not change.

## Verification

- `python -m pytest tests/test_run_record_no_false_failure.py tests/test_review_delegate.py -q`: 24 passed
- `python -m pytest -n auto tests/test_orchestration_guard_hooks.py tests/test_models_and_prompt.py -q`: 55 passed
- `specy-road file-limits`: OK
- Red/green: before the fix, `test_prompt_cli_run_that_filed_its_record_is_complete_with_no_error`
  failed with `['no review record was filed'] == [None]`.

## Added

- Guard `filed = exit_code == 0 and valid_record(...)[0]` in `close_reviewer_cli_run`: makes the attempt error `None` when the run filed its record for this commit (A1).
- Test `test_prompt_cli_run_that_filed_its_record_is_complete_with_no_error`: A1 success side (complete, no reason, no events, attempt error `None`, message absent from RUN json).
- Test `test_prompt_cli_clean_exit_without_a_record_says_no_record_was_filed`: A1 failure side (message present when no record exists).
- Test `test_prompt_cli_record_for_an_older_commit_is_not_this_commits_record`: A1 "for that commit" (a stale record still counts as missing).
- Test `test_delegate_run_that_filed_its_record_has_no_error_in_the_run_file`: the `review delegate` path also leaves no error on a completed run.
- Helper `_cli_repo` (test): a repo whose fake reviewer cli copies a prepared record into place and exits 0, so the prompt-cli path can be driven both ways.
- Helpers `_prompt_cli`, `_run_text` (test): run the reviewer cli channel and read the raw RUN json.
- Mocks: none (fake harness scripts only, and the delegate fake is reused from `tests/test_review_delegate.py`).
