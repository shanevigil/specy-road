# Implementation summary: M9.1 — land check on the merge commit

## What changed

- **`specy_road/finish_land_check.py`** (new): `resolve_land_check_cmd(repo_root, cli=)`
  (CLI wins, `''` turns the check off, else `land_check_cmd` in
  `roadmap/git-workflow.yaml`, same shape as `resolve_baseline_cmd`) and
  `run_land_check(tree, cmd)`. The check creates a detached worktree of
  `tree`'s HEAD (the new merge commit) in a temp dir and runs `cmd` once through
  the shell at `<worktree>/<project prefix>`. Output is streamed to stdout and the
  last 20 lines are kept. Only this invocation's worktree is removed
  (`worktree remove --force`, which also works when the directory is gone,
  then rmtree of its temp dir). Nothing repository-wide such as
  `worktree prune` runs, so other checkouts' stale registrations stay. Returns `None` on exit 0. Otherwise it
  returns an error naming the command, the exit code and the 20-line tail.
- **`specy_road/finish_land_integration.py`**: `_merge_and_push` records HEAD
  before the fast-forward and runs the check after
  `merge_feature_deterministically` and before `git push`. A failed check or a
  failed push runs `git reset --keep <pre>` in the tree holding the integration
  branch, adds the outcome to the error and pushes nothing. The push error says
  a re-run merges onto the new tip and checks it again. A failed check also
  restores `refs/remotes/<remote>/<integration>` to `tracking_before`,
  deleting it if it was absent. That undoes finish's fetches.
  `tracking_ref_snapshot` takes the snapshot before finish's first fetch:
  in `apply_on_complete_mode` before the push notice fetches, in
  `retry_merge_landing` before its fetch, and otherwise at the entry of
  `land_merge_feature_into_integration`.
  `land_merge_feature_into_integration` gains `land_check_cmd=None` (the CLI
  value) and resolves it once for both the holder path and the checkout path.
- **`finish_modes.py`**: `apply_on_complete_mode` and `retry_merge_landing` pass
  `land_check_cmd` through. `merge_landing_failed` includes
  `--land-check-cmd <quoted>` in the re-run command when the flag was given. Its
  "Fix the integration branch" wording became "Fix what the error above names",
  because a failed check is not a branch problem.
- **`feature_rm_registry.py`, `bundled_scripts/finish_task.py`**: thread
  `land_check_cmd` through the repeat-finish path
  (`_resolve_context` → `resolve_feature_rm_registry_context_for_finish` →
  `report_finish_already_done_on_branch` → `retry_merge_landing`), so the flag
  also applies on the re-run A4 asks for.
- **`bundled_scripts/finish_task_args.py`**: `--land-check-cmd CMD`
  (default `None`).
- **Schema** `land_check_cmd` (string). **Docs**: a *Land check on the merge
  commit* paragraph in `docs/git-workflow.md`. **CHANGELOG**: an Unreleased/Added
  entry.

## Decisions and interpretations

- **Reset target:** HEAD as recorded before `merge --ff-only`. This is the
  commit the local integration branch had before finish ran (A3). It is also
  pre-merge for A4.
- **Remote-tracking ref (A3, review R1):** on a failed check, the tracking
  ref is put back at the commit it had before finish's first fetch, even
  when that fetch found newer remote commits. A rejected push (A4) does not
  restore it: the re-run fetches anyway, and A4 asks only for the local
  reset.
- **Rejected push resets even when no check is configured.** A4 is stated
  unconditionally, and without the reset a re-run fails its `--ff-only`
  against the diverged local merge. Existing finish tests are unaffected.
- **`auto` mode** runs the check too (it takes the merge path first). A failed
  check falls back to the PR tail as any other merge failure does. pr mode
  never reaches the landing code.
- **Config is read from the finishing checkout's project root** (`repo`), as
  every other finish setting is, even when the merge lands in a holder
  worktree.
- **"Already up to date" merges** (no new merge commit) still run the check on
  HEAD before pushing.

## Final touch zones

`specy_road/finish_land_integration.py`, `specy_road/finish_land_check.py`,
`specy_road/bundled_scripts/finish_task_args.py`,
`specy_road/bundled_scripts/finish_task.py`, `specy_road/finish_modes.py`,
`specy_road/feature_rm_registry.py`,
`specy_road/templates/project/schemas/git-workflow.schema.json`,
`docs/git-workflow.md`, `CHANGELOG.md`, `tests/`. Untouched:
`sr/schemas/git-workflow.schema.json`, the toolkit roadmap's own copy, which is
outside the zones. Setting `land_check_cmd` in `sr/roadmap/git-workflow.yaml`
needs that copy refreshed (`refresh-schemas`) if the project validates against
it.

## Verification

- Review round 1 (`gpt-6.1-sol`, block) is addressed in `b50ee33`. R1 is the
  tracking-ref restore. R2 drops `git worktree prune`. X1 iterates
  `proc.stdout` directly. The first round's count of "18 tests" was wrong:
  that file had 16.
- `pytest -q -p no:cacheprovider tests/test_finish_land_check.py` at
  `b50ee33`: 22 passed (10 scenarios × 2 layouts + 2).
- Full `pytest` at `b50ee33`: not completed. Three foreground attempts (one
  serial run, one as 8 parallel file shards, and the four finish test files
  alone) were each killed at the tool's 20-minute ceiling. Load was 70–124
  from other agents' concurrent suites.
- Full `pytest` at `063825f`, before the review fixes (2569 tests, 223 files): all passed, none failed
  or errored. The machine had a load average of 30–90 from other agents, and
  Microsoft Defender scans every process spawn, so a serial run would have
  taken about 9 h. That is past the tool's 2 h background cap, and a single
  run was killed at 13%. The suite was therefore run as parallel per-file
  shards, each with its own `--basetemp`. When a shard was stopped at a cap,
  its in-progress file was re-run in a later shard. All 223 collected files
  completed in some shard. No temporary land-check worktree was left behind.
- `ruff check specy_road tests scripts`: pass. `specy-road file-limits`: pass.
  `scripts/check_test_private_imports.py`: 0 new.
- `scripts/check_clones.py`: could not run locally. `pylint` is not installed
  in this environment (FileNotFoundError), and CI installs it.

## Added

- `finish_land_check.resolve_land_check_cmd`: CLI-over-config resolution, kept out of `git_workflow_config.py` (near its 400-line cap).
- `finish_land_check._run_streaming`: shows a long gate's output live and keeps the 20-line tail A3 prints.
- `finish_land_check.run_land_check`: the detached-worktree check at the project root, with removal guaranteed (A1, A5).
- `finish_land_check.TAIL_LINES`: the 20 in A3, named once.
- `finish_land_integration.tracking_ref_snapshot`: records the tracking ref before finish's first fetch (R1/A3).
- `finish_land_integration._restore_tracking`: puts the tracking ref back on a failed check; it deletes the ref when it was absent (R1/A3).
- `tracking_before` keyword on `land_merge_feature_into_integration` and `_merge_and_push`, and the snapshot calls in `apply_on_complete_mode` and `retry_merge_landing`: carry the pre-fetch snapshot to the rollback (R1).
- `tests/test_finish_land_check.py::_other_lane`: a second clone that pushes to origin, shared by the race and stale-tracking inputs.
- Input added to `test_failing_check_pushes_nothing_and_restores_both_refs`: origin moved before finish, so the fetch advances origin/main (R1, both layouts).
- `test_finish_restores_the_tracking_ref_its_notice_fetched`: the same input through `apply_on_complete_mode`, whose push notice fetches first (R1, both layouts).
- `test_failing_check_leaves_an_absent_tracking_ref_absent`: the delete branch of `_restore_tracking` (R1, both layouts).
- `test_a_stale_registration_elsewhere_survives_the_check`: a pre-existing stale registration survives a failing and a passing check (R2/A5, both layouts).
- Removed: `git worktree prune` (R2) and the `or ()` fallback on `proc.stdout` (X1).
- `finish_land_integration._reset_integration`: `reset --keep` back to the pre-finish commit on check failure and on a rejected push (A3, A4).
- Branch in `_merge_and_push`: `if land_check_cmd` runs the check only when one resolved (A6).
- `land_check_cmd` keyword on `land_merge_feature_into_integration`, `_merge_and_push`, `retry_merge_landing`, `merge_landing_failed`, `report_finish_already_done_on_branch`, `resolve_feature_rm_registry_context_for_finish`, `finish_task._resolve_context`: carries `--land-check-cmd` to the landing on first finish and on re-run (A6).
- Branch in `merge_landing_failed`: names `--land-check-cmd` in the re-run so a re-run checks with the same command (A4).
- `--land-check-cmd` CLI flag (A6).
- Mocks: none. The tests use real git repos with a bare `origin`.
- `tests/test_finish_land_check.py::sandbox` fixture: an embedded/nested checkout with a bare origin (A7).
- `test_passing_check_runs_once_on_the_merge_commit_then_pushes`: A1, A2, A5, A7 (cwd is `<worktree>/<prefix>`, detached, before the push, pushed tip is the checked commit).
- `test_failing_check_pushes_nothing_and_restores_both_refs`: A3, A5, A7 (exit code, 20-line tail, both refs unchanged).
- `test_rejected_push_resets_and_a_rerun_checks_the_new_tip`: A4, A5, A7 (another lane pushes during the check; the re-run merges onto it and checks again).
- `test_check_runs_in_a_worktree_of_the_holders_merge`: A1, A3, A5, A7 when another worktree holds the integration branch.
- `test_configured_key_runs_without_a_flag`: A1 via the yaml key.
- `test_flag_overrides_the_key_and_empty_skips`: A6.
- `test_no_flag_and_no_key_runs_no_check`: A6 (off by default).
- `test_failure_names_the_rerun_with_the_flag`: A3/A4 stderr output and the re-run command.
- `test_parser_accepts_the_flag`: A6 parsing.
