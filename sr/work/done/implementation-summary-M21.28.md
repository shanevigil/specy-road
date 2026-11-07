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

## Fix round 2 (review gpt-6.1-sol-low, R1: symlink targets), superseded in round 3

Round 2 added a rule that snapshotted the in-repo real path behind each symlinked path. Round 3 removes that rule, and its `link` test row, in favour of the precondition below.

## Fix round 3 (coordinator: one rule for the class)

Class: a write destination that is not a regular file. Round 1 found a missing summary destination, round 2 a symlink target, and pre-existing directories were next. Instead of covering each destination's shape in the snapshot, finish now refuses them all before the first write, under one rule (`refuse_irregular_destinations_or_exit` in `finish_bookkeeping_undo.py`, docstrings on it and on `irregular_destination`):

- Every path in `write_destinations` must be absent or a regular file, reached through no symlink. That covers every manifest chunk (leaf and rolled-up ancestors), the registry, `roadmap.md`, `roadmap-context.md`, the PR-body file, the `work/done/` archive of a tracked summary, and the reviews-directory copy of an untracked summary.
- Each component under its base is checked with `lstat`. A symlink anywhere refuses, whether it points inside or outside the repo. The last component also refuses when it is a directory, FIFO, socket or device (one `_IRREGULAR` table). An absent component ends the walk.
- On a refusal, finish prints `error: finish-this-task writes there, but <path> is <kind>; make it a regular file or remove it` and `finish-this-task: nothing was changed`, then exits 1. This runs first in `bookkeeping_guard`, before `validate`, so a FIFO is never read.
- With that precondition, the snapshot and restore only ever see a regular file or an absence at each destination. `pre_commit_paths` now builds on `write_destinations` (one list of destinations, no duplicate), plus the cleanup and worker-log paths.
- Limits:
  - The cleanup *sources* (brief, prompt, summary, sidecar) are removed or moved, not written into, so they are outside the rule. M15.40's existing symlinked-brief handling, and its test, stay as they were.
  - The reviews root itself, which is the base for the reviews copy, is not checked component by component.
  - The rule checks every destination whatever the `on_complete` mode, so it can refuse a stray FIFO at `work/pr-body-<NODE>.md` even in merge mode.

## Fix round 4 (review gpt-6.1-sol-low, R1 and R2)

**R1 class: index entries that finish's staging reaches but the snapshot did not list.** `git add <dir>` stages every entry under a directory, including ones deleted on disk, so a snapshot built from the files on disk can never bound it. I removed the class rather than adding paths. `snapshot_pre_commit` now records the whole index file (`git rev-parse --git-path index`, which is per worktree and honours `GIT_INDEX_FILE`), and `restore_pre_commit` writes those exact bytes back (written beside the index and renamed into place). The per-path `ls-files`/`update-index` records, and the `../` index branch, are gone. Restoring the pre-run index, never HEAD, still keeps a user's staged edits. This is the only index writer between the snapshot and the commit, since the finish lock is held.

**R2 class: destination inspection failing, or a non-directory on the way.** `irregular_destination` is now one rule. Walking from the base with `lstat`, each component must be absent (the walk ends, because finish creates it) or the expected kind: a directory on the way, a regular file at the end. The `_KINDS` table names what it actually is. A symlink, a regular file where a directory belongs, a directory/FIFO/socket/device at the end, or an `lstat` error (named) all refuse. Anything else that can fail before the guarded body, namely computing the snapshot paths and reading the files and index, now refuses through the same exit path, `_nothing_changed`, which the destination refusal and the preflight validate also use: `error: …` then `finish-this-task: nothing was changed`, exit 1.

**Limit:** errors other than `OSError`, `subprocess.SubprocessError` and (at snapshot time only) `RuntimeError` are outside A3's bound. `RuntimeError` is caught at snapshot time because Python < 3.13 raises it for a symlink loop. The snapshot walks the same `removal_target` as cleanup, so a looping brief is refused before any write instead of failing mid-cleanup.

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

- Fix round 2, `roadmap.md` as a committed link to an in-repo `payload.md`, with digest refused after export wrote through the link: `payload.md` bytes, the index and HEAD are as before. The new public-entry row fails without the fix and passes with it.
- Fix round 2, a `roadmap/registry.yaml` symlink to `notes/reg.yaml`: `pre_commit_paths` adds `notes/reg.yaml` (scratch repo probe).
- Fix round 2, a `work/` directory symlink to `real_work/`: every work path (PR body, brief, prompt, summary, `work/done/` and reviews destinations) adds its `real_work/…` real path (same probe).
- Fix round 2, `roadmap-context.md` linking outside the repo (`/etc/hostname`): nothing is added and nothing outside the repo is snapshotted or restored (same probe).
- Fix round 2, a chunk symlink: `build_node_chunk_map` already returns resolved chunk paths, so the real target is what gets snapshotted. A chunk resolving outside `roadmap/` is skipped by both `build_node_chunk_map` and `find_chunk_path`, so finish never writes it (same probe).
- Fix round 2, cleanup removals through a link: `cleanup_paths` already adds `removal_target`, and the new rule only de-duplicates it.

- Fix round 3: a directory at `work/done/implementation-summary-M1.1.md`, `roadmap.md` linked to an in-repo `payload.md`, `roadmap-context.md` linked outside the repo, a FIFO at `work/pr-body-M1.1.md`. Each is refused before any write, naming the path and its kind, with worktree, index, HEAD and the outside target unchanged. Each of the four rows fails without the fix and passes with it.
- Fix round 3: the round-2 probes (symlinked registry, symlinked `work/` directory, link out of the repo) now meet the precondition. A symlink at the path or at any directory under the base refuses, so nothing is written behind a link and the round-2 real-path rule is gone.
- Fix round 3: existing tests with symlinks (`test_finish_merge_failure_undo` symlinked brief, `test_finish_work_cleanup`, `test_writers_refuse_links_out`) either use cleanup sources, which are outside the rule, or call the helpers directly. All still pass.

- Fix round 4, R1: tracked worker logs (`track_worker_logs: full`), with `a.log` deleted on disk and `b.log` present, so the log directory is staged, then the commit is refused. The index (still holding `a.log`), worktree and HEAD are as before. The public-entry row fails without the fix and passes with it.
- Fix round 4, R1: the other index writers before the commit are `git add` of the chunk, registry, generated files, cleanup removals and summary moves, plus anything a pre-commit hook stages. The whole-index restore covers all of them. The existing commit-refusal rows (staged and unstaged brief, tracked and untracked summary) still pass.
- Fix round 4, R1: the index location. From a nested project root (`sr/`), `git rev-parse --git-path index` returns `../.git/index`, relative to the root and resolved by `root / …`. From a linked worktree it returns the absolute per-worktree index. With `GIT_INDEX_FILE` set, it returns that path.
- Fix round 4, R2: `work/done` as a regular file. Finish is refused before any write with `work/done is a regular file, not a directory`, and worktree, index and HEAD are unchanged. The public-entry row fails without the fix (it previously raised `NotADirectoryError` with a traceback) and passes with it.
- Fix round 4, R2: an unreadable directory on the way (`chmod 000 work/done`) gives `… cannot be inspected (Permission denied), not a regular file`, with no traceback.
- Fix round 4, R2: a brief that is a symlink loop (a cleanup source, outside the destination rule), through finish's public entry: exit 1, `could not record the tree before writing: RuntimeError: Symlink loop …`, `nothing was changed`, no traceback, and status and HEAD unchanged.
- Fix round 4, R2: the other pre-guard steps. `write_destinations` reads the manifest, which `_resolve_main_context` already loaded, and `reviews_root` does not raise. Both run inside or before the new clean-exit path.

## Verification

- `pytest tests/test_finish_config_preflight.py`: 6 passed. With the package changes reverted, all rows failed. With only fix round 1 reverted, the 2 summary rows failed.
- Fix round 2: `pytest tests/test_finish_config_preflight.py`: 7 passed. With fix round 2 reverted, the link row failed.
- Fix round 4: `pytest tests/test_finish_config_preflight.py`: 12 passed. With round 4 reverted, the `file-as-parent` and `commit-worker-log-deleted-on-disk` rows failed. Full suite `pytest -n 4`: 5,691 passed. ruff and file-limits pass (`finish_bookkeeping_undo.py` at 400 lines).
- Fix round 3: `pytest tests/test_finish_config_preflight.py`: 10 passed. With round 3 reverted, the 4 rule rows failed. The full suite (`pytest -n 4`, 5,529 passed) ran before the last consolidation, which rebuilt `pre_commit_paths` on `write_destinations` and fixed the 400-line cap. After it, the targeted finish, nested-repo, gate and writer-link tests passed (230), as did ruff and file-limits.
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
- Fix round 2 (removed in round 3): the symlink-target rule and its `link` test row.
- Fix round 3: `write_destinations`, the one list of where finish writes, moves or copies into. `pre_commit_paths` reuses it.
- Fix round 3: `irregular_destination` and the `_IRREGULAR` table, one rule that walks the components and names a symlink, directory, FIFO, socket or device.
- Fix round 3: `refuse_irregular_destinations_or_exit`, which prints the refusal with nothing changed. It runs first in `bookkeeping_guard`.
- Fix round 3: test `test_refused_before_any_write`, one public-entry table. It replaces the separate rc4 test, which is now its `invalid-configuration` row, and adds the `directory`, `symlink-in-repo`, `symlink-out-of-repo` and `fifo` rows. Each asserts exit 1, the path and kind named, `nothing was changed`, and worktree, index, HEAD and the outside target unchanged.
- Fix round 3: test helper `_entry`, which describes a path without reading through a link, FIFO or directory, so `_state` never blocks on a FIFO.
- Test `test_failure_before_the_commit_restores_the_tree`, parametrized over 6 rows (A4):
  - a later validate refusal
  - a digest refusal after export rewrote `roadmap.md`
  - an `OSError` on the registry write
  - a commit refused by a pre-commit hook, in two rows. Both start with distinct staged and unstaged bytes on `work/brief-M1.1.md`, a path cleanup removes and stages.
    - (fix round 1, R1) tracked summary: cleanup moves it over an existing `work/done/` copy that has other bytes.
    - (fix round 1, R1) untracked summary: cleanup copies it into `work/reviews/M1.1/`, which was absent before.
- Test helper `_state` (fix round 1): also compares ignored files under `work/`, so the `work/reviews/` copy is checked. Each summary row also asserts that cleanup actually wrote its destination before the refusal.
- Branch in `snapshot_pre_commit` and `restore_pre_commit` (fix round 1): index records only for paths inside the worktree, because the main checkout's reviews directory has no index entry here.
- Mocks: the injection script patches the public `subprocess.check_call` (raising `CalledProcessError(3, argv)` for one named specy-road command) and `finish_task.write_registry` (raising `OSError`). The commit row uses a real pre-commit hook.
- Fix round 4: the whole-index snapshot (`PreCommitSnapshot.index_path` and `index_bytes`) and its restore, which replace the per-path index records, the `ls-files` call and the `../` branch (R1).
- Fix round 4: `irregular_destination` rewritten as one expected-kind rule, using the `_KINDS` table (which replaces `_IRREGULAR`) and an `OSError` branch that names the error (R2).
- Fix round 4: `_nothing_changed`, the one exit path for every refusal before a write (destinations, preflight validate, snapshot). It consolidates three copies of the print-and-exit (R2).
- Fix round 4: the snapshot in `bookkeeping_guard` is wrapped so that its `OSError`, `SubprocessError` or symlink-loop `RuntimeError` refuses cleanly (R2).
- Fix round 4: test row `file-as-parent` in `test_refused_before_any_write` (R2).
- Fix round 4: test row `commit-worker-log-deleted-on-disk` in `test_failure_before_the_commit_restores_the_tree`. The table's string `setup` branches became arrange functions (`_tracked_summary`, `_untracked_summary`, `_worker_log_deleted_on_disk`) with a `wrote` column, so the new row adds no branch (R1).
