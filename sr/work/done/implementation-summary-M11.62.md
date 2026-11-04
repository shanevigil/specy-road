# Implementation summary: M11.62 — headless-limits-denials

Branch `feature/rm-headless-limits-denials`. The coordinator told me to run `git merge origin/WIP/improvements-0-3-1`, and it fast-forwarded to `db320d0d`, so M8.2 and M11.59 are both in the base. Following the coordinator's scope note, this leaf implements only what M8.2 leaves out.

## What M8.2 already covers (no change here)

- **A1:** M8.2 covers all of it. `ClaudeCode._turn_signals` (`specy_road/worker_adapter_claude.py`) records one `permission_denied` event for each `permission_denials` entry, whatever the subtype or exit code. `worker_turn_check.close_turn` then flags the worker with `post_run_findings`. Replayed by `tests/test_worker_turn_check.py::test_claude_launch_and_resume_pass_mode_tools_and_no_prompts_and_a_denial_flags_the_worker`.
- **A2, partly.** M8.2 covers these cases:
  - a Claude result or `api_error` text that names a limit, including subtype success with exit 0 (`limit_detail` with `classify_limit`);
  - `system/api_retry` with `rate_limit`, plus the retry watchdog;
  - a Codex `turn.failed` with "try again in/at" (`_try_again` in `worker_adapter_parsers.py`);
  - `paused_by_limit` with `limit_reset_at`.
- **A4, partly.** M8.2 already makes Codex launches pass `CODEX_MEMORY_OFF` (`worker_adapter_codex.py`).
- **A3, executors.** M8.5 already sets `CLAUDE_CODE_DISABLE_BACKGROUND_TASKS=1` (and `CLAUDE_CODE_DISABLE_AUTO_MEMORY=1`) for Claude Code executors in `harness_env`.

## What this leaf adds

- **A2: exit 1 with no result line.** After a Claude turn that exits non-zero and logged no usage (a Claude result always carries usage, so no usage means no result line), the wrapper (`worker_runner._transcript_limit`) reads the session transcript. `ClaudeCode.transcript_limit` finds `~/.claude/projects/<project>/<session-id>.jsonl` by the session id alone and runs `limit_detail(failed=True)` on the last assistant message's text. A limit is recorded as a `usage_limited` event with source `claude-code transcript` and fed to the `TurnWatch`, so `close_turn` pauses the worker with the reset time. User entries (the prompt) are never read, and an id that is not `[A-Za-z0-9-]+` is refused, so it cannot act as a glob.
- **A2: Codex "try again at".** M8.2's parser already handled this; there was no replay test for the "at <time>" form, so I added one through the wrapper (a dated reset, compared against machine-local time).
- **A3: reviewers.**
  - `harness_env(..., "reviewer", harness="claude-code")` now sets `CLAUDE_CODE_DISABLE_BACKGROUND_TASKS=1` (`CLAUDE_REVIEWER_AVOID_ENV`), and `review delegate` passes the harness.
  - The bare reviewer command (`specy-road prompt --role reviewer --channel cli`, `role_prompt.run_bare_reviewer`) passes the same switch.
  - Reviewers do not get the auto-memory switch: `--bare` already turns auto memory off.
  - The "Backgrounded tests" paragraph of `docs/orchestration-workers.md` now says this.
- **A4.**
  - `harness_facts.unlisted_overrides(overrides, capture)` returns the `-c` keys whose feature the captured `codex features list` (`inventory-features.txt`) does not list. For `features.<name>` the feature is `<name>`; for any other key it is the table the key sits under (`memories.use_memories` belongs to `memories`).
  - `refresh-profiles --check` now also fails (exit 1, an `unlisted:` line per key) when a key in `CODEX_MEMORY_OFF` is unlisted.
  - The shipped capture lists `memories`, so all three keys pass today.
  - Documented in `docs/orchestration-models.md` and in the script's docstring and `--help`.

## Touch zones (final)

I added these with `specy-road edit-node M11.62 --add touch_zones=…` (commit `24cda199`):

- `specy_road/worker_adapter_claude.py`: since M11.59, Claude stream and session parsing lives here, not in `worker_adapters.py`.
- `specy_road/orchestration_role_env.py`: `harness_env` is where the harness environment's switches are set.
- `specy_road/review_delegate.py`: it builds the reviewer's environment and has to name the harness.
- `specy_road/bundled_scripts/role_prompt.py`: the bare reviewer command launches Claude itself.
- `specy_road/bundled_scripts/role_prompt_stream.py`: a new module. `role_prompt.py` was at the 400-line cap, so I moved `_stream_and_capture` here unchanged, apart from the new `env` parameter, as the public `stream_and_capture`.
- `specy_road/harness_facts.py`: the capture-reading helpers live here.
- `specy_road/bundled_scripts/refresh_profiles.py`: the `--check` command.
- `docs/orchestration-models.md`: the `refresh-profiles --check` docs.

Kept from the original list: `specy_road/worker_runner.py`, `docs/orchestration-workers.md` and `tests/`. `specy_road/worker_adapters.py` and `specy_road/worker_adapter_parsers.py` are unchanged; they are still listed but needed no edit.

## Verification

- `python -m pytest -n 4 -q -p no:cacheprovider` (the full suite): 3622 passed, 2 skipped.
- `specy-road file-limits`: OK. `worker_runner.py` is 395 lines, `role_prompt.py` 383.
- `ruff check specy_road tests/test_headless_limits_denials.py`: clean. `run()` stays under C901, which is why the transcript block is its own helper.
- `python scripts/check_test_private_imports.py`: 0 new private references.
- `specy-road validate`: OK.
- Red check: with the source changes taken out, 5 of the 8 new tests fail. The 3 that still pass test what M8.2 and M8.5 already cover, plus the negative transcript case.
- `specy-road refresh-profiles --check` on this checkout exits 1 already at the base, because of rendered-profile drift in `sr/model-profiles` that predates this leaf. It prints no `unlisted:` line. I did not use it as a verifier; the A4 tests cover the check.
- `scripts/check_clones.py` needs `pylint`, which is not installed here, so it was not run.

## Added

- `ClaudeCode.transcript_limit` (`worker_adapter_claude.py`): reads the last assistant message of the session transcript when there was no result line (A2).
- Session-id guard (`[A-Za-z0-9-]+`) in `transcript_limit`: the id becomes part of a glob pattern.
- Assistant-only filter in `transcript_limit`: the prompt (a user entry) can mention limits and must not pause the worker.
- `OSError` skip in `transcript_limit`: an unreadable transcript must not cost the turn its exit record.
- `worker_runner._transcript_limit` and its call in `run()` (Claude, non-zero exit, no usage logged): records the event and feeds the post-run check (A2). It is a separate helper so `run()` stays under ruff's C901 limit.
- `CLAUDE_REVIEWER_AVOID_ENV` and the reviewer branch in `harness_env` (`orchestration_role_env.py`): background tasks off for Claude reviewers (A3).
- `harness=h.harness` in `review_delegate._turn`: lets `harness_env` know the reviewer is Claude Code (A3).
- `env` in `role_prompt.run_bare_reviewer` and the `env` parameter of `stream_and_capture`: the bare reviewer command gets the same switch (A3).
- `role_prompt_stream.py` (`stream_and_capture` moved out of `role_prompt.py`): needed for the file cap.
- `harness_facts.CODEX_FEATURES_FILE` and `harness_facts.unlisted_overrides`: check override keys against the captured features list (A4).
- `refresh_profiles._check_overrides` and its use in `--check`: unlisted keys fail `--check` (A4).
- Mock change in `tests/test_review_files.py::_fake_run`: the fake `subprocess` is now also set on `role_prompt_stream`, where the moved `Popen` lives. The assertions are unchanged.
- `tests/test_headless_limits_denials.py`, with a fake harness on PATH that records the environment it was started with:
  - `test_exit_1_with_no_result_line_reads_the_limit_from_the_session_transcript`: A2, the transcript case.
  - `test_exit_1_whose_transcript_names_no_limit_stays_failed_and_the_prompt_is_not_read`: A2 negative; the prompt's limit wording is ignored.
  - `test_a_transcript_is_found_by_a_well_formed_session_id_only`: the session-id guard.
  - `test_a_codex_try_again_at_failure_pauses_the_worker_until_that_local_time`: A2, Codex "try again at" replayed through the wrapper.
  - `test_executor_launches_get_both_switches`: A3, the environment the wrapper really passes to an executor.
  - `test_review_delegate_and_the_bare_reviewer_command_disable_background_tasks`: A3, both reviewer paths.
  - `test_the_shipped_memory_overrides_are_all_listed_by_the_accepted_capture`: A4, the shipped keys pass and an unknown feature is reported.
  - `test_refresh_profiles_check_fails_on_an_override_the_capture_does_not_list`: A4, `--check` exits 1 with an `unlisted:` line per key.
