# Implementation summary: M21.42 — parse failures get the repair turn

Branch `feature/rm-parse-failure-gets-repair-turn`, base `721a0c55`, change commit `f845683c`; merged
`origin/WIP/improvements-0-3-1` (`8c28b00b`); fix round 1 commit `00e9c51d`.

## What changed

- `specy_road/review_record_write.py`
  - `Outcome.parse`: `final_answer`'s rerun reason when the answer itself did not parse. `file_review` sets it for
    every answer-level `Rerun` except `UNREADABLE_ANSWER`, which is an I/O error reading the run log. The write
    check still runs first, so an unparseable answer that wrote a file stays `review_failure`.
  - `repair_prompt(refusal, kind)`: `record` keeps M21.35's wording byte for byte. `parse` has the heading "Your
    final message could not be read". It introduces the reason as specy-road's reading of the final message, "not
    `review record`'s output", puts it in the same backtick fence, and asks for the whole JSON object with no code
    fence, no prose and nothing before or after it. It has no notes rules.
- `specy_road/review_delegate.py`
  - Repair condition (one rule since fix round 1): `_answer_failure(filed)` names the answer-level failure,
    `(refusal, "record")` or `(parse reason, "parse")`, else `None`. The repair turn launches only when there is
    one, the run holds no `refusal` yet, and the last attempt has `exit == 0` and is not a capacity error, for
    both kinds. These get no repair turn: chore runs (filed is `None`), capacity failures, non-zero exits
    (refused or unparseable), unreadable logs and review failures.
  - `_repair` stores the `(reason, kind)` it is given as `run["refusal"]` and `run["refusal_kind"]`. Repair attempts are still
    marked `repair: true` through `"refusal" in run`. A second failure of either kind names both reasons
    (unchanged join).
  - `_start` returns `(reason, kind)` for an incomplete run with a stored string refusal. A missing `refusal_kind`
    means `record`. The resume branch rebuilds the first reason per kind: the stored reason itself for `parse`, the
    M21.35 sentence for `record`. It joins on a second refusal or parse failure.
  - Module docstring updated.
- `docs/orchestration-reviewer-output.md`: the repair bullet is extended for parse failures, `refusal_kind`, resume
  and the cases with no repair turn.
- `CHANGELOG.md`: a `[Unreleased]` / Fixed entry.

## Touch zones (final)

These are the brief's zones plus the four test files the coordinator approved on 2026-11-06:
`tests/test_headless_limits_denials.py`, `tests/test_review_attempt_span.py`, `tests/test_review_delegate.py` and
`tests/test_review_record_write_closure.py`. `tests/review_delegate_helpers.py` was not changed: the existing
`raw` / `answer` steps produce every case. There are no new modules, and `file-limits` passes.

## Changed out-of-zone tests (coordinator-approved)

Each of the seven assertions below expected no second launch after a parse failure. Each one now asserts exactly one
repair launch whose prompt carries the parse reason, plus `refusal_kind == "parse"`. Every other assertion is kept.

1. `tests/test_review_delegate.py::test_a_retry_never_files_an_earlier_attempts_answer`: capacity flags
   `[True, False]` → `[True, False, False]`. Repair flags are `[False, False, True]`, and the last launch's prompt
   holds the reason.
2. `tests/test_review_delegate.py::test_a_clean_exit_without_a_record_is_incomplete`: the exact reason is now both
   reasons joined by "; after the repair turn, ". `len(attempts) == 1` → repair flags `[False, True]`, and the
   prompt holds the reason.
3. `tests/test_review_delegate.py::test_resume_continues_the_recorded_session`: its steps are now `{}, {}, verdict`
   (no JSON for the turn and its repair), so the first delegate still exits 1 and the `--resume` checks are
   unchanged. It adds the repair-flag, `refusal_kind` and prompt assertions for the first run.
4. `tests/test_review_record_write_closure.py::test_a_codex_resume_whose_last_answer_event_has_no_text_is_a_rerun`:
   `len(attempts) == 1` → repair flags `[False, True]` for `null_last`, still `[False]` otherwise. Codex reads its
   prompt from stdin, so the reason is checked in the `-repair.md` prompt file the resumed launch was given.
5. `tests/test_review_record_write_closure.py::test_a_retried_codex_turn_never_files_the_failed_fresh_turns_answer_file`:
   `[True, False]` → `[True, False, False]`, repair flags `[False, False, True]`, and the reason is in the
   `-repair.md` prompt file.
6. `tests/test_headless_limits_denials.py::test_review_delegate_and_the_bare_reviewer_command_disable_background_tasks`:
   the environment list goes from `* 2` to `* 3` (delegate's turn, its repair, then the bare reviewer command).
   The delegate run's repair flags are `[False, True]`, `refusal_kind` is `parse`, and the reason is in the repair
   prompt file.
7. `tests/test_review_attempt_span.py::test_two_real_attempts_each_have_their_own_span_and_only_the_last_is_read`:
   it now unpacks three attempts (the third is the repair), and the record's `log_end` check indexes attempt `[1]`
   rather than `[-1]` (same assertion, same attempt). It asserts the repair flag, `refusal_kind` and the reason in
   the prompt.

## Fix round 1 (gpt-6.1-sol-low block at bc53f0b1)

Finding: a schema-valid answer that `review record` refused, from a harness that exited non-zero, still got a
repair launch, because the clean-attempt gate applied only to parse failures. The class is "repair eligibility
decided per failure kind". Fix: one rule, `_answer_failure`, decides the failure for both kinds, and a single
clean-attempt gate decides the launch (`review_delegate._delegate_locked`). The resume join branch uses the same
helper. The docstring, the docs repair bullet and the CHANGELOG now say the clean-exit condition applies to both
kinds. This narrows M21.35: a refusal after a non-zero exit or a capacity failure no longer gets a repair turn,
which is what A1 requires. New row `refused-exit` in `test_no_repair_turn_without_a_refusal_or_a_clean_parse_failure`:
one launch, a `rerun` outcome, and a reason naming the refusal. It fails on `bc53f0b1`'s `review_delegate.py` and
passes now.

## Probes

- A refused answer with a non-zero exit (new `refused-exit` row): one launch, no repair turn. Pass; it failed before the fix.
- An unparseable answer with a non-zero exit (`exit` row): one launch. Pass, unchanged.
- Capacity retries exhausted (`capacity` row, retries=0): one launch. Pass. A refused answer cannot come with a capacity error's result line in the fake; the gate reads the same `capacity` flag for both kinds.
- A refusal or parse failure inside the repair turn itself: `_repair` launches nothing after it, whatever the exit. Checked by reading the code; the `test_a_second_failure_*` rows pass.
- `--resume` with a stored refusal: `_repair` writes the stored reason only after a clean attempt now. A legacy record that stored one after a non-zero exit is still resumed with the repair pair, because the user asked for `--resume`. Unchanged; the resume rows pass.
- `prompt --channel cli` (`run_and_file`): it has no repair path, so nothing reaches it. Checked with grep.
- Chore runs: `filed` is `None`, so `_answer_failure` returns `None`. `tests/test_chore_mode.py` passes.
- A last attempt with exit 0 that printed error events: this counts as clean under A1's literal "exited 0 with no capacity reason", so it is repaired. Documented here, not changed.
- Complexity: `_delegate_locked` still has one `if`/`elif`, as at the merge base. `ruff check specy_road tests scripts` is clean and `file-limits` is OK.

## Verification

- `python -m pytest -n 4 -q tests/`: 5837 passed (at bc53f0b1). Fix round 1: the targeted review-delegate tests
  (139) pass, and `ruff check specy_road tests scripts` is clean.
- `ruff check` on the changed Python files: clean. `specy-road file-limits`: OK.
- Red-green: with `f845683c`'s test files and the base package files, `tests/test_review_delegate_repair.py` gives
  14 failed and 13 passed.

## Added

- `Outcome.parse` field: carries the answer-level rerun reason so `review delegate` can tell a parse failure from a
  refusal (the planning sheet's Approach).
- `repair_prompt` `parse` branch: the parse-kind wording A2 requires, without the notes rules.
- `_answer_failure` helper in `review_delegate` (fix round 1): the one rule naming the answer-level failure and its
  kind for the repair launch and the resume join.
- `review_delegate` clean-attempt gate (last attempt exit 0, not capacity), applied to both kinds since fix round 1:
  A1's "exited 0 with no capacity reason".
- `review_delegate` `"refusal" in run` guard on the resume-join branch: a parse rerun on a run that is not being
  repaired (non-zero exit) must not reach the join.
- `_start` legacy-kind default (`record` when `refusal_kind` is missing): A2, for records written before this leaf.
- Test helper `_carries_parse` and `PARSE_INTRO` / `NO_JSON` constants in `tests/test_review_delegate_repair.py`:
  `_turns` checks the parse-kind repair prompt as it already checks the record kind.
- `_turns` change: it picks the prompt check by the run's `refusal_kind`, so every case still checks the prompts
  that were sent.
- Test helper `_valid_json`: the valid answer the fenced, prose-after and unfinished cases are built from.
- `test_a_second_refusal_leaves_the_run_incomplete_naming_both` → renamed
  `test_a_second_failure_leaves_the_run_incomplete_naming_both` and parametrized: refusal twice (the existing case),
  parse twice, parse then refusal, refusal then parse (A3).
- `test_an_unparseable_answer_gets_one_repair_turn_then_files` (new, parametrized): the fenced, prose-after,
  no-json, unfinished and schema-invalid rows. The schema-invalid row checks that the reason is fenced (A3).
- `test_no_repair_turn_unless_review_record_refused` → renamed
  `test_no_repair_turn_without_a_refusal_or_a_clean_parse_failure`. `no-json` moved to the repair table, and new
  rows cover `writes-unparseable` (review_failure, one launch), `capacity` and `exit` (no repair turn) (A3), and
  `refused-exit` (fix round 1: a refused answer with a non-zero exit gets one launch).
- `test_a_non_resumable_harness_gets_one_fresh_launch_with_the_full_prompt_and_the_refusal`: parametrized over
  `record` / `parse` (A3's non-resumable row).
- `test_resume_sends_the_repair_pair_for_the_stored_kind` (new, parametrized): resume with a stored parse reason,
  a resumed parse repair that fails again, and a legacy refusal with no `refusal_kind` (A3).
- Mocks: none added.
