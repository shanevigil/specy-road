# Implementation summary — M21.28 finish-validates-before-bookkeeping

## What changed

- `specy_road/bundled_scripts/finish_task.py`: `_finish_locked` wraps the PR-body write, the M15.40 merge-undo snapshot and `_bookkeeping_commit_phase` in `bookkeeping_guard(ROOT, node_id, sess_path)`. This runs after the branch, override and context checks (`_resolve_main_context`), and before the first write. The `_maybe_write_pr_body` call is compacted to 3 lines so the file stays under the 400-line cap. `_bookkeeping_commit_phase` and `_validate_export_digest` are unchanged.
- `specy_road/finish_bookkeeping_undo.py`:
  - `bookkeeping_guard` (context manager) first runs `preflight_validate_or_exit`. That runs `specy-road validate` with its output captured. On a non-zero exit it prints validate's stdout and stderr, then `finish-this-task: nothing was changed`, and exits 1 (A1).
  - The guard then snapshots `pre_commit_paths` with `snapshot_pre_commit` (A2).
  - If an `OSError` or `subprocess.SubprocessError` happens while HEAD is still the snapshot's HEAD, it prints the failing command (`specy-road validate|export|digest --repo-root …`, `git add …`, `git commit …`) or the error with its path. It then restores with `restore_pre_commit`, prints `error: could not restore <path>: <why>` for each path it could not put back, prints `nothing was committed; fix it and run finish-this-task again`, and exits 1 with no traceback (A3).
  - If HEAD has moved, the bookkeeping commit exists (for example a push or PR-integration failure after it), so the error propagates exactly as before. M15.40's post-commit undo is untouched.
  - `pre_commit_paths` lists:
    - every manifest chunk (the leaf's and any rolled-up ancestor's)
    - `roadmap/registry.yaml`
    - `roadmap.md` and `roadmap-context.md` (`GENERATED_COMMITTED`)
    - `work/pr-body-<NODE>.md`
    - the cleanup paths and worker logs, through `_cleanup_and_log_paths`, which is factored out of `snapshot_bookkeeping` so both snapshots share it
    - (fix round 1) both places cleanup writes a summary to: `archived_implementation_summary_rel` (`work/done/`, where a tracked summary is moved) and `reviews_dir(root, node)/implementation-summary-<NODE>.md` (where an untracked summary is copied). Both come from the helpers cleanup itself uses.
  - `snapshot_pre_commit` stores each path's `_path_state` (bytes, symlink or absent) and, for paths inside the worktree, its `git ls-files -s --full-name` records. From a linked worktree, `reviews_dir` is the main checkout's (`../…` relative), so that path has only a worktree state and no index entry, and it is left out of `ls-files` and `update-index`.
  - `restore_pre_commit` removes those index entries and re-adds the recorded ones with `git update-index -z --index-info` (top-relative, so it works for a nested project root). It then rewrites each worktree path with the existing `_restore`. It never restores from HEAD, so staged and unstaged edits survive.
- `CHANGELOG.md`: an entry under [Unreleased] Fixed (A5).

Deviation from the planning sheet's Approach (the plan-review decisions win): there is no `git restore --source=HEAD`. The snapshot is restored instead (G-R11).

## File-limits note

`specy-road file-limits` in this checkout reads `sr/constraints/file-limits.yaml`, where the cap is still 400. `finish_task.py` was already at 400 lines, so the new logic lives in `finish_bookkeeping_undo.py`, which is inside the touch zones. `finish_task.py` is now 397 lines. No new module was needed.

## Touch zones (final)

`specy_road/bundled_scripts/finish_task.py`, `specy_road/finish_bookkeeping_undo.py`, `tests/test_finish_config_preflight.py`, `CHANGELOG.md`: unchanged from the brief.

## Fix round 1 (review gpt-6.1-sol-low, R1)

Class: paths that cleanup *writes as a destination* before the commit. The snapshot covered the paths it removes, but not the paths it moves or copies into. I audited every writer between the snapshot and the commit (see Probes). The two summary destinations were the only ones missing, and both are now in `pre_commit_paths`. The directories that cleanup creates for them with `mkdir` (`work/done/`, `work/reviews/<NODE>/`) can stay behind empty after a restore. They hold no bytes and no index entries, so they are out of A2's scope. M15.40's post-commit undo (`snapshot_bookkeeping`) is unchanged, as the brief marks it out of scope.

## Probes

- `_maybe_write_pr_body` writes `work/pr-body-<NODE>.md`: in the snapshot (unchanged).
- `_update_chunk_status` and `complete_rolled_up_ancestors` write chunk files: every manifest chunk is in the snapshot (unchanged).
- `_save_registry` writes `roadmap/registry.yaml`: in the snapshot (unchanged).
- `export` and `digest` write `roadmap.md` and `roadmap-context.md`: in the snapshot. The only other writes are to the gitignored derived `.specyrd/cache/`, which is not bookkeeping.
- `cleanup_work_artifacts`, removals (brief, summary, symlink targets): in the snapshot through `cleanup_paths` (unchanged).
- `cleanup_work_artifacts`, `_archive_tracked_summary` moving to `work/done/implementation-summary-<NODE>.md`: was missing, now added. The tracked row covers it, with an existing destination that has other bytes. It fails without the fix and passes with it.
- `cleanup_work_artifacts`, `_keep_untracked_summary` copying into `reviews_dir/<NODE>/`: was missing, now added. The untracked row covers it, with the destination absent before. It fails without the fix and passes with it.
- `cleanup_session_sidecar` removing the sidecar: in the snapshot through `cleanup_paths` (unchanged).
- `worker_logs_to_stage` and `git add` (index only): the worker logs are in the snapshot, and every snapshotted path's index entries are restored (unchanged).
- `merge_undo_snapshot` and `warn_if_pr_body_tracked`: these only read, so there is nothing to snapshot.
- A linked worktree, where `reviews_dir` is outside the worktree: I ran `pre_commit_paths` and `snapshot_pre_commit` on this worktree. They returned `../../../../work/reviews/M21.28/implementation-summary-M21.28.md` with state `absent`, no index entry, and no `ls-files` error.

## Verification

- `pytest tests/test_finish_config_preflight.py`: 6 passed. With the package changes reverted, all rows failed. With only fix round 1 reverted, the 2 summary rows failed.
- Fix round 1: `pytest -n 4` over the preflight, `test_finish_*`, nested-repo finish and land, gate-agreement and file-limits tests: 199 passed.
- `pytest -n 4` (full suite): 5460 passed.
- `ruff check specy_road tests scripts`: clean.
- `specy-road file-limits`: OK.

## Added

- `bookkeeping_guard` (finish_bookkeeping_undo): runs the preflight validate, takes the snapshot, and restores on a pre-commit failure (A1, A3).
- `preflight_validate_or_exit`: runs validate with captured output before any write (A1). Its `OSError`/`SubprocessError` branch makes a validate that cannot start exit cleanly too.
- `_failed_step`: names the failing command the way the dev types it, or the error with its path (A3).
- HEAD-moved guard in `bookkeeping_guard`: never restores the pre-commit state once the bookkeeping commit exists, so post-commit failures behave as before.
- `PreCommitSnapshot`, `pre_commit_paths`, `snapshot_pre_commit`, `restore_pre_commit`: the snapshot and restore of worktree bytes and index entries (A2, A3).
- `_cleanup_and_log_paths`: factored out of `snapshot_bookkeeping` so both snapshots share one path list (reuse, A2).
- Test `test_rc4_configuration_is_refused_before_any_write`: the rc4 configuration gives exit 1, names the fix, leaves the registry entry and the tree unchanged, and prints no traceback (A4).
- Test `test_failure_before_the_commit_restores_the_tree`, parametrized over 5 rows (A4):
  - a later validate refusal
  - a digest refusal after export rewrote `roadmap.md`
  - an `OSError` on the registry write
  - a commit refused by a pre-commit hook, in two rows. Both start with distinct staged and unstaged bytes on `work/brief-M1.1.md`, a path cleanup removes and stages.
    - (fix round 1, R1) tracked summary: cleanup moves it over an existing `work/done/` copy that has other bytes.
    - (fix round 1, R1) untracked summary: cleanup copies it into `work/reviews/M1.1/`, which was absent before.
- Test helper `_state` (fix round 1): also compares ignored files under `work/`, so the `work/reviews/` copy is checked. Each summary row also asserts that cleanup actually wrote its destination before the refusal.
- Branch in `snapshot_pre_commit` and `restore_pre_commit` (fix round 1): index records only for paths inside the worktree, because the main checkout's reviews directory has no index entry here.
- Mocks: the injection script patches the public `subprocess.check_call` (raising `CalledProcessError(3, argv)` for one named specy-road command) and `finish_task.write_registry` (raising `OSError`). The commit row uses a real pre-commit hook.
