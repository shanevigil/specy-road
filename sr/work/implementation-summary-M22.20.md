# Implementation summary: M22.20 (terminate-and-finish-rollback-robustness)

## What changed

### A1: `worker terminate` (`specy_road/worker_process.py`)

- **Same schedule.** `end_group` takes `also` (escaped pids and their start times). On each pass it sends SIGTERM and then SIGKILL to the group and to every listed escaped pid together. It waits until both are gone. Before, the escaped pids were signalled only after the group's grace had run out.
- **Zombies.** The inventory now reads `stat` (`pid=,ppid=,pgid=,stat=,lstart=`). An escaped pid in state `Z` is not a survivor. `_group_members` also skips zombies, which matches `_exists`.
- **Failed inventory is sticky.**
  - A failed `ps` listing sets `descendants_unchecked: true` on the record before the group is signalled. The group is still ended, as the existing test requires, and terminate raises, so the record is not marked terminated.
  - `process_alive` returns true while that mark is set, so the next `terminate` calls `kill_group` again.
  - If the group is gone by then, `kill_group` runs only the descendant pass. The walk also starts from the recorded pgid, harness pid and wrapper pid, but only when no live process holds that pid; a held pid is a reused one.
  - The mark is cleared only after a listing succeeds and no escaped pid survives.
  - Coordinator decision (b): processes that were re-parented are out of reach, and that limit is accepted.
- The record field is `WorkerRecord.descendants_unchecked: bool | None` in `specy_road/worker_state.py`, added to `specy_road/schemas/worker-record.schema.json` as `["boolean","null"]`. Both zones were added by the coordinator.

### A2: finish rollback (`specy_road/finish_bookkeeping_undo.py`)

- **No unlink first.** `_restore` writes a temp file or link beside the path (`.<name>.<hex>.specy-road-restore`, `O_EXCL`), chmods it, and renames it over the path with `os.replace`. If that fails, the path keeps its old bytes and the error names the temp file, which is kept. Only a path that was absent before is unlinked.
- **Modes.** Both snapshots (`BookkeepingSnapshot.modes`, `PreCommitSnapshot.modes`) record each regular file's permission bits, and the restore applies them. A file with the right bytes but the wrong mode is rewritten too.
- **Index guard.**
  - The snapshot records the staged entries from `git ls-files -s -z --full-name -- :/` (mode, object id, stage, top-relative path).
  - It also records the paths finish owns: `pre_commit_paths` plus `work/worker-logs/<node>/`, all top-relative.
  - Before restoring, any entry that changed outside the owned paths causes a refusal (an index that cannot be listed counts as changed). The current index stays in place, the pre-finish index is saved next to it (`index.before-finish.*`), and the message names the changed paths and both files.
  - Entries are compared rather than index bytes, so a hook that only runs `git status` (a stat refresh) still gets the full restore. The commit rows of the existing test now run `git status` in the hook to check this.

### Docs

- `docs/orchestration-workers.md`: updated the paragraph "Processes outside the group".
- `CHANGELOG.md`: added a [Unreleased] Fixed entry.

## Final touch zones

The original seven plus `specy_road/worker_state.py` and `specy_road/schemas/worker-record.schema.json`, both added by the coordinator. `tests/test_finish_merge_failure_undo.py` was not changed; it passes as is. No file-limit split was needed.

## Verification

- `python -m pytest -q -n 4 tests/test_worker_terminate_descendants.py tests/test_finish_config_preflight.py tests/test_finish_merge_failure_undo.py`: 47 passed.
- The wider set (every `tests/test_worker*`, `test_finish*`, `test_review_delegate*`, `test_review_record*`, `test_schema*`, `test_reviewer*`): 901 passed, 8 skipped.
- `ruff check specy_road tests scripts`: clean. `specy-road file-limits`: OK.
- Red/green, each run against the old module at HEAD~1:
  - The fork-during-grace test fails, with SIGTERM arriving about 3.2 s after the start against a 3 s grace.
  - The modes row, the hook-staging test and the restore-OSError test all fail.

## Added

### Package
- `worker_process.end_group(also=...)`: escaped pids signalled on the group's schedule (A1).
- `worker_process._signal`: one signalling loop for the group and the escaped pids; it keeps `end_group` under ruff's complexity limit.
- `worker_process._end_with_descendants`: the inventory, the combined end, the survivor check and the mark, shared by the normal path and the repeat pass (A1).
- `worker_process._mark_unchecked`: persists and clears `descendants_unchecked`, saved only when `repo_root` is given (A1).
- `worker_process._running` / `_listed`: survivor checks that skip zombies; `_listed` tolerates a failed `ps` during the wait loop, and the final check raises instead (A1).
- `worker_process._INVENTORY`: one inventory argv that now includes `stat` (A1).
- Branch in `kill_group`: a marked record whose group is gone runs only the descendant pass (A1, repeat).
- Guard in `_escaped_descendants(recorded=...)`: recorded pids that no live process holds become roots (A1, links that still hold).
- `process_alive`: true while `descendants_unchecked` is set, so `terminate` does not mark the worker terminated (A1).
- `WorkerRecord.descendants_unchecked` and its schema property: the record field the acceptance names (A1).
- `finish_bookkeeping_undo._record`: the snapshot entry plus the regular-file mode (A2, modes).
- `_restore(mode=...)`: temp file and `os.replace`, mode applied, temp path named on failure (A2).
- `PreCommitSnapshot.modes`, `.index_entries`, `.owned`; `BookkeepingSnapshot.modes` (A2).
- `snapshot_pre_commit(owned_dirs=...)`: the worker-logs directory that finish stages as a whole (A2, index guard).
- `_index_entries`, `_foreign_staging`, `_keep_both_indexes`: the index guard and how both indexes are named (A2).

### Tests
- `test_worker_terminate_descendants.py`:
  - `_seams` takes `stat=` and `dies=`, and the inventory row format now includes `stat`.
  - `test_a_same_start_survivor_raises_naming_its_pid` is parametrized with a zombie kept by a subreaper (A3).
  - `test_a_failed_inventory_is_repeated_by_the_next_terminate` (A3).
  - `test_an_escaped_child_gets_sigterm_with_the_group_not_after_its_grace` with the `FORKING` harness: a real setsid child that forks only on SIGTERM (A3).
- `test_finish_config_preflight.py`:
  - `_entry` also compares permission bits.
  - `_pre_commit_hook` helper; the commit rows' hook runs `git status` first, the stat-refresh case where the restore must not refuse.
  - New row `commit-file-modes`, through the `_modes` arrangement (A3).
  - `test_staging_by_the_hook_is_kept_and_both_indexes_named` (A3).
  - `test_a_failed_restore_write_keeps_the_previous_bytes`, with `os.replace` stubbed (A3).
- Mocks: `os.replace` is patched in one test, and `subprocess.run` / `os.kill` are patched through the existing `_seams`.
