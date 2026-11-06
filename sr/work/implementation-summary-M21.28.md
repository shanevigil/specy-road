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
    - the cleanup paths and worker logs, through `_cleanup_and_log_paths`, which is factored out of `snapshot_bookkeeping` so both snapshots share it.
  - `snapshot_pre_commit` stores each path's `_path_state` (bytes, symlink or absent) and its `git ls-files -s --full-name` records.
  - `restore_pre_commit` removes those index entries and re-adds the recorded ones with `git update-index -z --index-info` (top-relative, so it works for a nested project root). It then rewrites each worktree path with the existing `_restore`. It never restores from HEAD, so staged and unstaged edits survive.
- `CHANGELOG.md`: an entry under [Unreleased] Fixed (A5).

Deviation from the planning sheet's Approach (the plan-review decisions win): there is no `git restore --source=HEAD`. The snapshot is restored instead (G-R11).

## File-limits note

`specy-road file-limits` in this checkout reads `sr/constraints/file-limits.yaml`, where the cap is still 400. `finish_task.py` was already at 400 lines, so the new logic lives in `finish_bookkeeping_undo.py`, which is inside the touch zones. `finish_task.py` is now 397 lines. No new module was needed.

## Touch zones (final)

`specy_road/bundled_scripts/finish_task.py`, `specy_road/finish_bookkeeping_undo.py`, `tests/test_finish_config_preflight.py`, `CHANGELOG.md`: unchanged from the brief.

## Verification

- `pytest tests/test_finish_config_preflight.py`: 5 passed. With the package changes reverted, all 5 failed.
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
- Test `test_failure_before_the_commit_restores_the_tree`, parametrized over 4 rows (A4):
  - a later validate refusal
  - a digest refusal after export rewrote `roadmap.md`
  - an `OSError` on the registry write
  - a commit refused by a pre-commit hook. This row starts with distinct staged and unstaged bytes on `work/brief-M1.1.md`, a path cleanup removes and stages.
- Mocks: the injection script patches the public `subprocess.check_call` (raising `CalledProcessError(3, argv)` for one named specy-road command) and `finish_task.write_registry` (raising `OSError`). The commit row uses a real pre-commit hook.
