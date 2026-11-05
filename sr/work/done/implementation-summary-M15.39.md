# Implementation summary — M15.39 failed-roadmap-write-restores-every-file

## What changed

- `specy_road/bundled_scripts/roadmap_chunk_atomic.py` (A1): `AtomicWritePlan.write()` sets `_staged = True` right after `_snapshot()`, before the first byte is written. `commit()` runs `write()` and `validate()` inside one `try`, so an exception from either one rolls back and is re-raised. `rollback()` restores every snapshotted path (chunks, manifest, sidecar text and staged deletions) byte-for-byte, unlinks paths that did not exist before, and now also unlinks every `.<name>.tmp-*` file the plan created. `_snapshot()` uses `os.path.isfile` in place of `Path.is_file`: on Python 3.11 a name the OS refuses (ENAMETOOLONG) made `Path.is_file` raise during the snapshot. With `os.path.isfile` it counts as a new path, and its write then fails and rolls back.
- `specy_road/bundled_scripts/roadmap_crud_ops.py` (A2): `cmd_add` and `cmd_edit` catch `(ValueError, OSError)`, so a failed write prints one `error: <message>` line and exits 1, with no traceback.
- `write_with_routing` and `write_node_update` (in `roadmap_chunk_router.py`, outside the touch zones) were not changed. Both call `plan.commit`, so every caller of the plan gets the rollback: GUI add, brainstorm promote, move and remove.

## Touch zones (confirmed)

`specy_road/bundled_scripts/roadmap_chunk_atomic.py`, `specy_road/bundled_scripts/roadmap_crud_ops.py`, `tests/test_roadmap_crud_atomicity.py`. No other file needed a change.

## Verification

- `pytest tests/test_roadmap_crud_atomicity.py`: 16 passed. Full suite `pytest -n 4`: 4910 passed. `specy-road file-limits` passes, and so does `ruff check` on the changed files.
- Red/green: with the two source files reverted, tests (b) and (c) fail. With only the `commit()` change reverted, test (a) fails.

## Added

- `AtomicWritePlan.tmp_paths` field: records each temp file so rollback can remove one left by a failed write or `os.replace` (A1).
- `_staged = True` moved to before the write loop: rollback now runs after a part-way write (A1).
- `write()` moved inside `commit()`'s `try`: a write failure rolls back like a validation failure (A1).
- Temp-file unlink loop in `rollback()`: no `.tmp-` file is left behind (A1).
- `os.path.isfile` in `_snapshot()`: an over-long name no longer raises before the snapshot is taken (A1, and needed for test (a)).
- `OSError` added to the `except` in `cmd_add` and `cmd_edit`: one error line, exit 1 (A2).
- Test helper `_roadmap_bytes`: byte snapshot of every file under `roadmap/` (A3b, A3c).
- Test `test_plan_write_failure_restores_the_chunk_and_removes_temp_files` (A3a).
- Test `test_add_node_write_failure_restores_the_roadmap`: planning/ is a regular file (A3b).
- Test `test_edit_node_sheet_rename_failure_restores_the_roadmap`: planning/ is read-only; skipped as root or on Windows (A3c).
- Mocks: none.
