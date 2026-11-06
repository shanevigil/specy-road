# Implementation summary: M21.27 — filings take the review lock

## What changed

- `specy_road/review_lock.py` (new; added to touch zones by the coordinator): `review_run_lock(reviews, wait=0)`,
  `ReviewRunBusy`, `FILING_WAIT = 10` and `filing_busy(node_id)`. The lock moved out of
  `specy_road/review_record_write.py`, which would otherwise exceed the 400-line file limit; `review_record_write`
  re-exports `ReviewRunBusy` and `review_run_lock`, so existing importers (`review_delegate`, `role_prompt`, tests)
  are unchanged. `wait` retries the non-blocking flock every 0.1 s until the deadline; the default of 0 keeps the
  run's immediate `ReviewRunBusy` (A1).
- `specy_road/bundled_scripts/review_cli.py`: new argparse handler `cmd_review_record_locked` for `review record`.
  It resolves the node id against the roadmap before any mkdir or lock file (an unknown, absolute or `..` id exits 1
  with `unknown node id: <ID>` and creates nothing), then takes the leaf's lock with `FILING_WAIT` and calls
  `cmd_review_record`. On busy it exits 1 with `a reviewer run on <ID> holds work/reviews/<ID>/; nothing was
  written — file again when it ends (review list <ID>)`. `cmd_review_record` itself stays lock-free: `file_review`
  calls it inside the run's own lock (plan-review G-R6), so the run's own filing still files (A1, A2).
- `specy_road/review_gate_ready.py`: `write_human_approval` writes `REVIEW-human.md` inside the same lock with
  `FILING_WAIT`; busy raises `ReviewRunBusy` before writing.
- `specy_road/bundled_scripts/mark_implementation_reviewed.py`: catches `ReviewRunBusy` with `SigningError` (one
  handler, to stay under the C901 complexity limit) and exits 1 with the same sentence, no traceback (A2).
- `docs/orchestration.md`: one sentence in the `review record` section (appended to the existing paragraph to stay
  under the file limit). `CHANGELOG.md` [Unreleased] Fixed entry (A4).
- Tests, existing (added to touch zones by the coordinator): `tests/test_review_file_case.py` now accepts
  `.review-run.lock` beside `REVIEW-opus.md`. `tests/test_review_rejected_m15_33.py` now asserts that no
  `REJECTED-ghost.md` and no `REVIEW-*` file was written, rather than that the directory does not exist. A filing now
  creates the leaf's lock file; nothing else in either test changed.

## Final touch zones

specy_road/review_record_write.py, specy_road/review_lock.py, specy_road/bundled_scripts/review_cli.py,
specy_road/review_gate_ready.py, specy_road/bundled_scripts/mark_implementation_reviewed.py,
tests/test_review_concurrent_writers.py, tests/test_review_file_case.py, tests/test_review_rejected_m15_33.py,
docs/orchestration.md, CHANGELOG.md.

## Verification

- `pytest -q tests/test_review_concurrent_writers.py tests/test_review_file_case.py tests/test_review_rejected_m15_33.py tests/test_review_delegate.py tests/test_mark_implementation_reviewed_gate.py tests/test_review_record_write.py tests/test_prompt_channel_cli_run.py`: passes.
- Full suite `pytest -n 4`: 5522 passed (after merging origin/WIP/improvements-0-3-1).
- `ruff check specy_road tests scripts` and `specy-road file-limits`: clean.
- Without the package change, 3 of the 7 new tests fail (no `FILING_WAIT`, no `wait=`); the other 4 guard the default
  path and pass either way.

## Added

- `review_lock.py` module: holds the lock so `review_record_write.py` stays within the file limit.
- `review_run_lock(wait=…)` retry loop: lets a filing wait briefly for another filing (A1).
- `FILING_WAIT` constant: the 10 s filing wait; the test patches it to 0 (A1, A3).
- `filing_busy()` helper: the one refusal sentence shared by `review record` and the human approval (A2).
- `cmd_review_record_locked` handler: takes the lock in the CLI only, so `file_review` inside a run is not refused (A1, G-R6).
- Node-id guard in that handler: no mkdir or lock file for an unknown, absolute or `..` id (A1, G-R7).
- `ReviewRunBusy` catch in `mark_implementation_reviewed`: exits 1 with the sentence and no traceback (A2, G-R8).
- Test `test_filings_wait_for_and_refuse_during_a_reviewer_run`: delegate with a fake harness gated by ready/release files; `review record` (plain, `FILING_WAIT`=0) and the human approval are refused with the hand-off bytes unchanged; afterwards the run is complete, `REVIEW-opus.md` is filed, and `review record` succeeds (A2, A3).
- Test `test_lock_wait_against_another_process` (2 rows): a second process releases within the wait (acquired) or holds past it (`ReviewRunBusy`) (A3).
- Test `test_two_filings_started_together_both_file`: two concurrent `review record` processes both file (A3).
- Test `test_unknown_absolute_or_dotdot_id_creates_nothing` (3 rows): absolute, `..` and unknown ids exit 1 and create nothing (A3).
- Mocks: `FILING_WAIT` patched to 0; `sys.stdin.isatty` and `builtins.input` patched to drive the interactive human approval, as `test_mark_implementation_reviewed_gate.py` does.
