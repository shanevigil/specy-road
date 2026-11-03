# Implementation summary: M11.19 (`pickup-no-work-stash`)

## Scope

Acceptance **A1** only: prove that a real `specy-road do-next-available-task` pickup does not stash `work/` and does not lose concurrent appends to a worker event log under `work/.workers/`.

## Touch zones (confirmed)

| Path | Change |
|------|--------|
| `tests/test_registry_commit_scope.py` | Added concurrent-append pickup regression test |
| `specy_road/bundled_scripts/do_next_task_pickup_helpers.py` | No edit — `register_and_commit` already commits only the registry (`--` path scope) |
| `specy_road/bundled_scripts/do_next_task.py` | No edit — pickup documents no stash of `work/` |
| `specy_road/worker_reconcile.py` | No edit — no stash involvement |

## Behaviour

Added `test_pickup_leaves_worker_events_and_stash_alone_while_the_log_grows`: frees the dogfood-style review repo leaf, creates a worker record, runs `--local` pickup on `dev` while a background thread appends `output` events during the registry `git commit` window (short delay injected only in the test’s `git_run` wrapper so the race is reliable). Asserts contiguous event sequences, every appended line present on disk, `last_event_seq` matches the log, and `git stash list` is empty.

## Verification

- `pytest tests/test_registry_commit_scope.py`
- `specy-road file-limits`

## Added

- `_free_leaf_for_pickup` helper in `tests/test_registry_commit_scope.py` — shared setup to clear registry and reset leaf status before pickup (`reason`: same steps as existing local-pickup tests, keeps the new test focused on concurrency).
- `test_pickup_leaves_worker_events_and_stash_alone_while_the_log_grows` — A1 regression through public pickup CLI (`reason`: only missing coverage per planning audit; production fix already landed in rc2).
- Test-only `git_run` wrapper that sleeps on `commit` and sets `during_commit` (`reason`: deterministic overlap with registry commit without mocking pickup selection or registry logic).
- Background thread appending worker events while pickup runs (`reason`: reproduces the field failure mode where a live worker wrote during stash/restore).
