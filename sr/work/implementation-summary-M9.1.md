# Implementation summary: M9.1 — land check on the merge commit

## What changed

- **`specy_road/finish_land_check.py`** (new): `resolve_land_check_cmd(repo_root, cli=)`
  (CLI wins, `''` turns the check off, else `land_check_cmd` in
  `roadmap/git-workflow.yaml`, same shape as `resolve_baseline_cmd`) and
  `run_land_check(tree, cmd)`. The check creates a detached worktree of
  `tree`'s HEAD (the new merge commit) in a temp dir and runs `cmd` once through
  the shell at `<worktree>/<project prefix>`. Output is streamed to stdout and the
  last 20 lines are kept. The worktree is always removed (`worktree remove
  --force`, `worktree prune`, rmtree). Returns `None` on exit 0. Otherwise it
  returns an error naming the command, the exit code and the 20-line tail.
- **`specy_road/finish_land_integration.py`**: `_merge_and_push` records HEAD
  before the fast-forward and runs the check after
  `merge_feature_deterministically` and before `git push`. A failed check or a
  failed push runs `git reset --keep <pre>` in the tree holding the integration
  branch, adds the outcome to the error and pushes nothing. The push error says
  a re-run merges onto the new tip and checks it again.
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
- **Remote-tracking ref (A3):** finish never pushes on failure, so the tracking
  ref does not move. The fetch at the start of finish can still advance it
  when the remote really did move; that is the existing behaviour.
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

- `pytest tests/test_finish_land_check.py` (18 tests, both layouts): pass.
- Full `pytest` at `063825f` (2569 tests, 223 files): all passed, none failed
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
