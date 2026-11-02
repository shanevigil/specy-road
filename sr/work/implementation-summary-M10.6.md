# Implementation summary: `M10.6` — Measure whether lower reviewer effort changes verdicts

Branch `feature/rm-measure-whether-lower-reviewer`, base `d9fc67a57eccdbd9a05bb3d40595b8f7dfba65b9`,
implementation commits `6792da65`, `b689f2d7` (round 2) and `e0c71b64` (round 3).

## Acceptance

- **A1** — `scripts/review_effort_study.py NODE_ID... --model ID [--model ID] --levels L1 L2`
  replays each `work/reviews/<ID>/PACKET.md` through each roster reviewer at both levels
  and writes `results.csv` (`node_id, commit, model, family, level, verdict, block_reasons,
  exit_code, seconds`), one row per packet, level and model. It runs only the roster
  entry's `channels.cli` through `substitute_prompt`. A level reaches the command as
  M10.5 passes effort: `{effort}` → the harness's flag (`claude-code`, `codex`). The
  command must name `{effort}`, otherwise both levels would run the same command and
  the script refuses. On Cursor, whose model ids carry the effort, the roster id's
  `-<level>` suffix is swapped in the command. The reviewer gets a study preamble and the
  packet, judges from the packet alone, files nothing, runs in its own directory under
  `-o`, and ends with a YAML `verdict`/`block_reasons` block. Before the first run, the
  script checks roster role, command, packet, and the `--max-runs` budget (default 12).
  If any check fails, nothing runs.
- **A2** — `docs/design-notes/reviewer-effort-study.md` covers the protocol, the decision
  rule, the packets (`M3.16` `89bd140`, `M9.1` `ea48cee`, `M3.13` `b28c198`, full SHAs in
  the note) and the 12-row results table. It records **12 of 12 budgeted runs** and gives
  a decision per family: xai and openai meet the rule (same verdict on every packet;
  Sol's one block names the same defect at both levels). For both, a medium reviewer is
  a Cursor roster choice, not a profile default. Claude was not measured.
- **A3** — The four shipped Claude profiles keep their `effort_by_role` values. Each
  line's comment now says the reviewer was kept, not lowered, by M10.6 and cites the note.
  It still names M10.6, which `test_shipped_claude_profiles_set_default_effort_and_coordinator_one_below`
  checks.

## Round 2 (REVIEW-gpt-6.1-sol, block, R1)

- **R1 fixed in `b689f2d7`:** `main` resolves the study directory to an absolute path. Each
  reviewer runs with its own directory as cwd, so a relative `-o` used to pass a prompt path
  the reviewer could not open. The study was not re-run (the budget is spent); the recorded
  runs used an absolute `-o`, so their results stand.
- The tests' fake reviewer now reads the prompt file it is given (a missing file fails the
  run). A new test runs with a relative `-o` and checks that every row has a parsed verdict
  and exit 0. With the round-1 script, that test fails.

## Round 3 (REVIEW-gpt-5.6-sol-high, block, A1)

- **Duplicate `--levels` fixed in `e0c71b64`:** `plan` refuses two equal levels, before the
  output directory is created or any reviewer runs. Before the fix, `--levels high high` ran
  one level twice under one run directory and read as a two-level study. The study was not
  re-run; the recorded runs used `high medium`.
- A new test runs the script as a subprocess (the real CLI) with `--levels high high` and
  checks for exit 1, the refusal message and no output directory. With the round-2 script,
  that test fails.

## Deviations and notes for the coordinator

- **Sol ran on Cursor, not Codex.** The roster's `gpt-6.1-sol` command
  (`sr/tools/codex-review.sh gpt-6.1-sol "<prompt>"`) names no `{effort}`. The script
  refuses it (verified, no run spent). The openai family was measured through the
  roster's Cursor entry `gpt-5.6-sol-high`. Measuring GPT-6.1 Sol on Codex needs
  `{effort}` in that roster `channels.cli` and in the wrapper, both outside this leaf's
  touch zones. The note says so.
- **The executor picked the packets** (the approach has a human pick them), within the
  budget. The note says so, and the command to rerun is in it.
- **Not indexed in `docs/design-notes/README.md`.** That index is outside the touch
  zones; a one-row addition there is a follow-up.
- Raw run output (prompt and reply per run, CSVs) is untracked, at
  `/private/tmp/claude-501/-Users-savigil-WORKSPACE-specy-road-sr-work--worktrees-effort-study/be5896dc-3aac-4bcc-afe5-67df5ab33c6f/scratchpad/study/`.

## Touch zones (confirmed)

`scripts/review_effort_study.py`, `docs/design-notes/reviewer-effort-study.md`,
`specy_road/templates/project/model-profiles/` (only the four `anthropic-claude/*.md`
changed), `tests/test_review_effort_study.py`. Nothing else changed.

## Verification

- Round 3: `.conda/bin/pytest tests/test_review_effort_study.py -q`: 12 passed
- Round 2: `pytest tests/test_review_effort_study.py -q`: 11 passed
- Round 1: `pytest tests/test_review_effort_study.py tests/test_models_and_prompt.py -q`: 35 passed
- Round 1: `pytest -q` (full suite): 2989 passed, 2 skipped
- `ruff check scripts/review_effort_study.py tests/test_review_effort_study.py`: clean
- `specy-road file-limits`: OK
- `python scripts/check_test_private_imports.py`: 0 new
- `scripts/check_clones.py` did not run here: `pylint` is not installed in this environment

## Added

### Helpers (scripts/review_effort_study.py)
- `level_command`: turns a roster entry and a level into the command and its effort args (`{effort}` flag, or Cursor id-suffix swap); refuses a command that cannot vary the level.
- `packet_commit`: reads the commit under review from a packet, for the CSV and the note.
- `parse_verdict`: reads the last fenced YAML verdict block of a reply; `unparsed` when there is none.
- `plan`: budget, roster, role, command and packet checks before any reviewer runs.
- `run_one`: runs one reviewer in its own directory, keeps prompt and output, returns the CSV row.
- `main`: argument parsing and CSV writing.
- `StudyError`, `ID_LEVELS`, `COLUMNS`, `PREAMBLE`: refusal type, Cursor effort suffixes, CSV header, study prompt.

### Branches / guards
- Flag harness whose `channels.cli` lacks `{effort}` → refused (two levels would be one command).
- Cursor id without a `-<level>` suffix, or not present in the command → refused.
- Two equal `--levels` (round 3) → refused before anything runs (one level twice is not a two-level study).
- Study over `--max-runs` → refused whole (maintainer's 12-run budget).
- Non-reviewer roster id or missing packet → refused before any run.
- Study directory resolved to an absolute path (round 2, R1) → a relative `-o` still gives each reviewer a prompt path it can open from its own cwd.
- Reviewer timeout → row with `exit_code: timeout`, output kept.

### Mocks
- `fake.py` in the tests: a stand-in reviewer command that records its argv in its run directory, reads the prompt file it is given, and prints a verdict block (or exits 3 with none).

### Tests (tests/test_review_effort_study.py)
- `test_flag_harness_passes_each_level_through_effort_and_writes_one_row_per_run`: A1 rows, columns and `{effort}` expansion.
- `test_relative_output_dir_still_hands_each_reviewer_a_readable_prompt`: R1, a relative `-o` with a reviewer that reads its prompt.
- `test_cursor_level_swaps_the_effort_suffix_of_the_model_id`: Cursor's level is carried by the model id.
- `test_flag_harness_without_effort_placeholder_is_refused_before_any_run`: no silent same-command study.
- `test_cursor_id_without_effort_suffix_is_refused`: the Cursor guard.
- `test_duplicate_levels_are_refused_through_the_cli_before_anything_runs`: round 3, duplicate levels through the CLI.
- `test_study_over_budget_is_refused_whole`: the budget guard.
- `test_non_reviewer_and_missing_packet_are_refused`: roster and packet checks.
- `test_reply_without_verdict_block_is_unparsed_with_exit_code`: an unreadable reply is recorded, not dropped.
- `test_last_verdict_block_wins`: parse rule when a reply has several blocks.
- `test_script_imports_no_network_or_model_client`: A1's "never a model API".
- `test_shipped_claude_effort_by_role_cites_the_study_note`: A3.
