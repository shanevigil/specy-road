# Implementation summary: M11.7 — review delegate

## What changed

- **A1:** `specy-road review delegate <ID> --model <roster id>` (new `specy_road/review_delegate.py`, registered under `review` in `review_cli.py`). It builds the reviewer prompt with `role_prompt.build_prompt(role="reviewer")`, so the reviewer keeps the packet-only, edit-nothing rules and the role/substitution/sensitivity checks. It runs the roster `preflight`, then launches the entry's harness through the worker adapters. A `claude-code` entry without `channels.cli` runs bare through `ClaudeCode.reviewer_launch`, which now takes an optional `session=(id, resume)`. That option adds `--session-id`/`--resume` and stream-json output so the id can be read back. Other entries use `adapter.launch`/`adapter.resume` with `channels.cli` or the harness default. The command waits for the turn. It records the run in `work/reviews/<ID>/RUN-<model>.json` (the commit, the native session id, each attempt and the final state) and the raw output in `RUN-<model>.log`. `--resume` continues the recorded session with a continue prompt. It is refused when there is no session, when the harness differs, or when the run was for another commit. A harness without resume exits 2.
- **A2:** an attempt that fails (non-zero exit or an error event) with capacity or rate-limit wording (`429`, `529`, `overloaded`, `rate limit`, `usage limit`, `quota`, `RESOURCE_EXHAUSTED`) is retried at most `--retries` times (default 3). The wait is `--backoff` seconds (default 30), doubled each time. A retry resumes the reported session, or starts fresh when the harness reported none. The run is `complete` only when a valid `REVIEW-<model>.md` for the commit under review exists afterwards (exit 0). Otherwise it is `incomplete` with a reason (exit 1). An interrupt or a launch refusal also closes the record as incomplete. `handoff status` lists each run (`review_runs` in `--json`, with `current`) and adds a problem for an incomplete run at the commit under review. Without a claim, each record line now names its commit (`at <sha>, not evaluated`). `review list` marks a record that is not for the commit under review `stale` and prints the runs. With a claim, an old record was already shown only as a stale problem, never in `reviews`, and the tests now cover that after a failed delegated run.
- **A3:** `docs/orchestration-review.md` has a new section, "Delegating a reviewer". `tests/test_review_delegate.py` uses a fake claude-code harness (`channels.cli` with `{session_flag}`) for success, a capacity error then success (with backoff and session resume), bounded retries, a run that writes no record (including an older block left in place), resume, and the refusals.

## Touch zones (confirmed)

`specy_road/review_delegate.py` (new), `specy_road/bundled_scripts/review_cli.py`, `specy_road/worker_adapters.py`, `docs/orchestration-review.md`, `tests/test_review_delegate.py`. `specy_road/review_files.py` needed no change: run files use their own `RUN-` prefix, which its listers already ignore. Nothing outside the touch zones was changed.

## Notes

- `review_cli.py` (400 lines), `worker_adapters.py` (399) and `review_files.py` (399) sit at the 400-line cap. To make room, the logic went into the new module, and the three identical `node_id`/`--ref` subparsers in `review_cli.build_parser` became one loop. No limit or exemption was raised.
- I added no `noqa` comments.
- Compatible with M8.3 (structured reviewer output): a run's outcome is read only through `list_reviews`/`load_review`, so any change to the record schema applies here too.
- Capacity detection matches wording, and only on a failed attempt. A failure whose output happens to contain such a word is retried, but at most `--retries` times.
- Verification: `pytest tests/test_review_delegate.py` passed (9). `tests/test_review*.py`, `test_models_and_prompt.py`, `test_lean_gates.py` and `test_mark_implementation_reviewed_gate.py` gave 471 passed, 2 skipped. `tests/test_worker*.py`, the file-limits tests and the stale-commands tests gave 210 passed. The doc and CLI tests gave 95 passed. `specy-road file-limits` is OK, `ruff check specy_road tests` is clean, and `check_test_private_imports.py` reports 0 new. `scripts/check_clones.py` could not run here because pylint is not installed. The full suite was not run in one go: there is no xdist, and it is longer than one foreground command.

## Added

- `specy_road/review_delegate.py` — the command's module (kept out of `review_cli.py`, which is at the line cap).
- `RUN_PREFIX`, `run_path`, `load_run`, `_read_json`, `_save` — the per-model run record under the hand-off directory (A1/A2), written atomically.
- `CAPACITY` / `capacity_error` — recognises provider capacity and rate-limit wording (A2).
- `RESUME_PROMPT` — continue prompt for `--resume` and for capacity retries in a reported session.
- `DelegateError` — refusals with the sentence the CLI prints.
- `_entry`, `_preflight` — roster lookup and the entry's preflight. These are local because `worker_ops`' versions are private and raise `WorkerError`.
- `_Harness` — chooses bare Claude Code or the adapter's launch/resume, with the profile's api id, reviewer effort and launch mode.
- `_turn` — runs one turn, logs raw output and collects the session id, error texts and the output tail.
- `valid_record` — whether a valid `REVIEW-<model>.md` exists for the commit under review (A2's complete vs incomplete).
- `_start` — prompt text and the session to resume; refuses a resume with no session, another harness or another commit.
- `_attempts` — the bounded retry loop with doubling backoff and session resume (A2).
- `_prompt_file` — writes the reviewer and continue prompts under `work/`.
- `delegate` — the operation. A `BaseException` guard closes the record as incomplete on an interrupt or a launch refusal.
- `run_states`, `run_lines`, `run_problems` — the run listing for `handoff status` and `review list` (A2).
- `cmd_review_delegate`, `add_parser` — CLI entry and `review delegate` arguments.
- `ClaudeCode.reviewer_launch(..., session=)` — the optional session flag and stream-json output; behaviour without it is unchanged.
- `review_cli`: `review_runs` and run problems in `_node_status`; `review_runs` and each record's `commit` in `_unclaimed`; the `at <sha>, not evaluated` and run lines in `_render`; the stale marker and run lines in `cmd_review_list`; the subparser loop (line budget).
- `tests/test_review_delegate.py` — fake claude-code harness script `FAKE` (mock harness, a step per call, logs argv). Tests:
  - `test_success_builds_the_prompt_launches_and_records_the_session`: A1.
  - `test_a_capacity_error_is_retried_with_backoff_and_resumes_the_session`: A2.
  - `test_capacity_retries_are_bounded_and_end_incomplete`: A2.
  - `test_a_run_that_writes_no_record_is_incomplete_and_never_shows_the_old_verdict`: A2/A3.
  - `test_a_clean_exit_without_a_record_is_incomplete`: A3, no retry for a non-capacity failure.
  - `test_resume_continues_the_recorded_session`: A1.
  - `test_refusals`: unrostered model; resume unsupported → exit 2.
  - `test_bare_reviewer_launch_tracks_a_session_only_when_asked`: adapter change.
  - `test_capacity_error_reads_provider_wording`: classifier.
