# Implementation summary: M11.74 — pickup-finish-shared-lock

## Goal

Serialize `do-next-available-task`, `finish-this-task`, and `abort-task-pickup` in a shared checkout so branch switches and integration-branch commits cannot interleave.

## Approach

Added `specy_road/repo_lock.py` with a FIFO ticket queue and exclusive holder file under `<git-common-dir>/specy-road/repo-lock/`. Each command acquires the lock before any git write, prints the holder pid and operation while waiting, times out after two hours, and clears holders or queue tickets whose pid no longer exists.

Wrapped the git-mutating bodies of the three bundled entrypoints in `pickup_finish_lock`. Documented the behaviour in `docs/git-workflow.md` beside the concurrent-lanes registry merge note.

## Touch zones (confirmed)

- `specy_road/bundled_scripts/do_next_task.py`
- `specy_road/bundled_scripts/finish_task.py`
- `specy_road/bundled_scripts/abort_task_pickup.py`
- `specy_road/repo_lock.py` (new)
- `docs/git-workflow.md`
- `tests/test_repo_lock.py` (new)

No additional paths were required.

## Verification

- `specy-road file-limits` — exit 0
- `python -m pytest tests/test_repo_lock.py -q` — exit 0

## Acceptance

- **A1:** All three commands take the shared lock before branch switches or integration commits; waiters queue in ticket order with timeout and holder messaging; stale holders and dead waiters are cleared. Tests cover two concurrent processes and a stale holder left by a dead pid.

## Added

- `pickup_finish_lock` context manager in `repo_lock.py` — exclusive pickup/finish/abort serialization with FIFO tickets and stale pid cleanup.
- `lock_root` in `repo_lock.py` — resolves `<git-common-dir>/specy-road/repo-lock/` and ensures queue directory exists.
- `RepoLockTimeout` in `repo_lock.py` — non-zero exit when the wait exceeds `DEFAULT_TIMEOUT_S`.
- `_run_pickup` in `do_next_task.py` — pickup body run under the repository lock after `ROOT` is resolved.
- `_finish_locked` in `finish_task.py` — finish body run under the repository lock after branch validation.
- `_abort_locked` in `abort_task_pickup.py` — abort git mutations run under the lock after preflight checks.
- `test_two_concurrent_callers_serialize` in `tests/test_repo_lock.py` — two processes cannot increment a shared counter concurrently while holding the lock.
- `test_stale_holder_from_killed_process_is_cleared` in `tests/test_repo_lock.py` — dead holder pid and orphan ticket are cleared so the next caller acquires.
