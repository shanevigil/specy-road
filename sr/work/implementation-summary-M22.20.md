# Implementation summary: M22.20 (terminate-and-finish-rollback-robustness)

## What changed

### A1: `worker terminate` (`specy_road/worker_process.py`)

- **One listing rule at every step (`_Descendants`).**
  - Each listing reads `ps -A -ww -o pid=,ppid=,pgid=,stat=,lstart=` and walks parent links from three starting points:
    - the group's members;
    - every escaped descendant already found that still runs with its recorded start time;
    - each recorded pid (pgid, harness, wrapper) that no live process holds. A pid that a live process holds is a reused one and is never a starting point.
  - Every process reached outside the group joins the set with its start time.
  - A pid counts as running only with that start time and not in `Z` state.
- **Schedule.**
  - `kill_group` takes one snapshot listing before the first signal.
  - `end_group(outside=found.live)` then lists again at each step, both SIGTERM and SIGKILL, and during each wait. It signals the group and the escaped pids together.
  - As a result, a child that a known escaped descendant forks during the grace gets the SIGKILL step.
  - `outside()` returning `None` (ps failed) means "cannot say": the wait goes on, and the step counts as unchecked.
- **Zombies.** `Z` entries are no survivors, whether outside the group or in it (`_group_members` reads `stat`).
- **Sticky mark.**
  - The record gets `descendants_unchecked: true` at the start of the pass.
  - It is cleared only when the pass ends with every listing read and no survivor.
  - Any failure at any step leaves the mark set and raises, so the record is not terminated.
  - `process_alive` is true while the mark is set. The next `terminate` repeats the pass, and runs only the descendant part when the group is already gone.
  - Coordinator decision (b): a process re-parented before any listing reached it is out of reach, and that limit is accepted.
- The record field is `WorkerRecord.descendants_unchecked: bool | None` (`specy_road/worker_state.py`), with a matching schema property (`["boolean","null"]`).

### A2: finish rollback (`specy_road/finish_bookkeeping_undo.py`)

- **No unlink first.** `_restore` writes a temp file or link beside the path (`.<name>.<hex>.specy-road-restore`, `O_EXCL`), chmods it, and replaces the path with `os.replace`. On failure the old bytes stay, and the temp file is kept and named. Only a path that was absent before is unlinked.
- **Modes.** Both snapshots record each regular file's permission bits, and the restore applies them.
- **Index: one rule.**
  - The snapshot records the staged entries (`git ls-files -s -z --full-name -- :/`).
  - At restore time, if those entries changed, `_save_changed_index` first copies the current index next to it (`index.left-by-finish.*`). It prints a `note:` that names the changed paths and both files, then puts the snapshot index back. An index that cannot be listed counts as changed.
  - If the copy cannot be written, the index stays as it is and the restore reports `could not restore the index`.
  - A stat-only refresh (`git status` in the hook) leaves the entries equal, so the restore is whole and no copy is written.
  - This rule replaces round 0's split between paths finish owns and foreign paths.

### Docs

- `docs/orchestration-workers.md`: updated the paragraph "Processes outside the group".
- `CHANGELOG.md`: added a [Unreleased] Fixed entry.

## Fix round 1 (gpt-5.6-sol-high at 1194573f)

| Finding | Class | Fix |
|---|---|---|
| Child forked during the grace survives | A process that appears after the single snapshot | The listing is repeated at every step, starting from the processes already found (`_Descendants`). The fork test now asserts `_gone(forked)`. |
| A transient ps failure after the snapshot lets the next terminate mark the worker terminated | A listing failure at any step other than the first | The mark covers the whole pass and is cleared only after every listing succeeds. |
| Hook staging on a path finish owns is discarded | Staging that cannot be told apart from finish's own (same path, worktree-consistent) | Owner classification is dropped. Any change to the staged entries saves and names the replaced index before the restore. |
| Fork test had no no-survivor assertion | Test integrity | Added `assert _gone(forked)`. |

Finding 3 is broader than the review says. Telling a hook's staging apart from finish's own `git add` on the same path would need the index captured right after that `git add`, which happens in `specy_road/bundled_scripts/finish_task.py` (outside the zones). The save-and-name rule avoids needing to know who staged what, so it needs no change outside the zones.

## Probes

- Fork-during-grace with a real setsid child that forks on SIGTERM, harness ignoring TERM, grace 3 s: no WorkerError, the escaped child and the forked child are both gone. Against the 1194573f module: `assert _gone(forked)` fails.
- ps failing at every listing of the first terminate: the record stays `running` with `descendants_unchecked: true`; the second terminate signals the fake descendant, ends `terminated`, and clears the mark. This passes on both modules.
- ps failing after a successful snapshot (the reviewer's transient case): same result as the previous probe. Against 1194573f it fails with "cannot recheck pid(s) … failed" and the mark is lost.
- Descendant whose start time changed between the snapshot and the first signal: never signalled, no survivor (existing test, unchanged). Checked because the step listings now drive the signalling.
- A zombie kept by a subreaper: terminate succeeds (parametrized existing test).
- Unreadable first inventory: the group is still ended and terminate raises "could not list its descendants" (existing test, unchanged).
- Hook staging on an unrelated path, on `roadmap.md` (a path finish writes), and under `work/worker-logs/M1.1/` (a directory finish stages): each time the note names the path, the saved index holds the hook's blob ("hook bytes"), and the index and files are back as before. All three fail against 1194573f.
- A hook running only `git status`, plus a staged/unstaged brief: full restore, no `could not restore`, the state is identical (existing commit rows).
- Restore write raising OSError (stubbed `os.replace`): the previous bytes stay, and the named temp file holds the snapshot's bytes. The undo path (`undo_bookkeeping`) shares `_restore` and is covered by `tests/test_finish_merge_failure_undo.py`, which passes unchanged.
- Executable and 0600 cleanup files after a failing pre-commit hook: modes restored (row `commit-file-modes`).
- Reviewer runners (`review_record_write.end_group(pid, grace)` with no `outside`): signature-compatible; the wider run including `test_review_record*` passes.
- Complexity: no changed function is more complex than at the merge base (ruff C901 at max 0: `end_group` 6 vs 8, `kill_group` 4 vs 4, `_restore` 7 vs 7, `restore_pre_commit` 5 vs 5).

## Final touch zones

The original seven plus `specy_road/worker_state.py` and `specy_road/schemas/worker-record.schema.json`, both added by the coordinator. `tests/test_finish_merge_failure_undo.py` was not changed and passes. No file-limit split was needed.

## Verification

- `python -m pytest -q -n 4 tests/test_worker_terminate_descendants.py tests/test_finish_config_preflight.py tests/test_finish_merge_failure_undo.py`: all pass.
- Wider run (every `tests/test_worker*`, `test_finish*`, `test_review_delegate*`, `test_review_record*`, `test_schema*`, `test_reviewer*`): 913 passed, 8 skipped.
- `ruff check specy_road tests scripts`: clean. `specy-road file-limits`: OK.

## Added

### Package
- `worker_process._Descendants` (`live`, `_running`): the one listing rule, re-run at every step; the set grows; failures recorded in `failed` (A1).
- `worker_process.end_group(outside=...)`: callable for the escaped pids at every step; `None` keeps waiting (A1, replaces round 0's `also`).
- `worker_process._signal`: one signalling loop for the group and the escaped pids.
- `worker_process._end_with_descendants`: the snapshot, the combined end, the survivor and failure checks, and the mark, shared by the normal path and the repeat pass (A1).
- `worker_process._mark_unchecked`: sets the mark at the start of the pass and clears it at the end; saved only with `repo_root` (A1).
- `worker_process._INVENTORY`: the one inventory argv, including `stat`.
- Branch in `kill_group`: a marked record whose group is gone runs only the descendant pass (A1, repeat).
- `process_alive`: true while `descendants_unchecked` is set (A1).
- `WorkerRecord.descendants_unchecked` and its schema property (A1).
- `finish_bookkeeping_undo._record`: the snapshot entry plus the file mode (A2).
- `_restore(mode=...)`: temp file and `os.replace`, mode applied, temp path named on failure (A2).
- `PreCommitSnapshot.modes`, `.index_entries`; `BookkeepingSnapshot.modes` (A2).
- `_index_entries`, `_save_changed_index`: the index rule (A2). Removed in round 1: `_foreign_staging`, `_keep_both_indexes`, `PreCommitSnapshot.owned`, `snapshot_pre_commit(owned_dirs=)`.

### Tests
- `test_worker_terminate_descendants.py`:
  - `_seams` takes `stat=`, `dies=` and `outage=` (`{"on", "ok"}`: reads fail after the first `ok` while on), and its rows now include `stat`.
  - `test_a_same_start_survivor_raises_naming_its_pid` is parametrized with a zombie kept by a subreaper (A3).
  - `test_a_failed_inventory_is_repeated_by_the_next_terminate` is parametrized: every listing fails, or failures start after the snapshot (A1, A3).
  - `test_an_escaped_child_gets_sigterm_with_the_group_not_after_its_grace` with the `FORKING` harness asserts SIGTERM inside the grace and no survivor, the forked child included (A3).
- `test_finish_config_preflight.py`:
  - `_entry` compares permission bits.
  - `_pre_commit_hook` helper; the commit rows' hook runs `git status` (the stat-refresh case).
  - Row `commit-file-modes` (A3).
  - `test_staging_by_the_hook_is_saved_and_named`, parametrized over an unrelated path, a path finish writes and the worker-logs directory (A2, A3).
  - `test_a_failed_restore_write_keeps_the_previous_bytes`, with `os.replace` stubbed (A3).
