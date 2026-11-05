# Implementation summary: M15.40

finish-this-task: a failed merge landing reports after the land check output and undoes its bookkeeping commit.

## What changed

- **A1 (output order).** Took the "flush stdout before each stderr message" option rather than line-buffering in `finish_task.main`, because `specy_road/bundled_scripts/finish_task.py` sits at the 400-line cap in `sr/constraints/file-limits.yaml` (the effective cap for this checkout). `finish_land_check._run_streaming` flushes after each line it copies. `merge_landing_failed` (used by both the merge path and the retry path), the `auto` fallback error, and `refuse_unless_finish_tip` flush stdout before they write to stderr. A pipe shared by stdout and stderr now ends with the outcome.
- **A2 (undo).** New module `specy_road/finish_bookkeeping_undo.py`. Before the bookkeeping phase, finish records the HEAD sha and the bytes of the files that phase removes or archives: `work/brief-`, `prompt-` and `implementation-summary-<ID>.md`, the on_complete session sidecar, and this leaf's `work/worker-logs/<ID>/`. It takes this snapshot only in merge mode and not for a rollup (`merge_undo_snapshot`). If `land_on_integration` fails or raises in merge mode, `apply_on_complete_mode` calls `undo_bookkeeping`, which checks out the feature branch if needed, runs `git reset --keep <pre-sha>` and writes the files back. `merge_landing_failed(..., undo=(sha, failure|None))` then names a plain `specy-road finish-this-task`. It adds `--on-complete merge --override-on-complete` only when merge was an override of the configured mode, because a plain re-run would otherwise use the configured mode. If the undo fails, it prints `error: could not undo the bookkeeping commit: ...` and names `git reset --keep <sha>`.
- **A3.** `retry_merge_landing` is unchanged and still calls `merge_landing_failed` without `undo`, so its message ("bookkeeping is already committed, retries only the landing") is the same. auto and pr pass no snapshot and keep their commit. Step 9 of `docs/dev-workflow.md` now describes the undo, the plain re-run, the undo-failure reset and the retry for branches an earlier finish left committed.
- **A4.** `tests/test_finish_merge_failure_undo.py` runs finish in a sandbox with a bare remote and a passing `land_check_cmd`, with stderr merged into stdout. Case (a) uses a pre-receive hook. Case (b) runs finish through `python -c` with `specy_road.finish_modes.land_on_integration` patched to run the real land check and then raise `OSError`. Each case asserts exit 1, finish's `error: could not land merge to dev:` line after the check output with the reason in it (`remote rejected` / `OSError: simulated landing crash`), the branch tip equal to its pre-finish sha, a clean tree, the registry claim held, and the brief and summary restored byte for byte (not archived under `work/done/`).

## Touch zones (final)

These are as listed. The new module `specy_road/finish_bookkeeping_undo.py` was already in the zones. No file outside them changed.

## Verification

- `python -m pytest -n 4 -q`: 4906 passed.
- `specy-road file-limits`: OK.
- Red-green: with the flushes in `finish_modes.py` and `finish_land_check.py` removed, both sandbox tests fail on ordering. With the snapshot disabled (`undo = None`), both fail on the branch tip and registry.

## Existing tests adjusted

- `tests/test_branch_cleanup.py::test_a_retried_landing_deletes_the_branch` and `tests/test_prerelease_s2.py::test_rerunning_finish_retries_a_failed_merge_landing` test the retry of a branch already left on its bookkeeping commit. A2 means a current finish no longer leaves that state. Each test now patches `finish_task.merge_undo_snapshot` to return `None`, which simulates an earlier finish, so the retry path (A3) is still covered with every original assertion unchanged.

## Added

- `specy_road/finish_bookkeeping_undo.py` `BookkeepingSnapshot`: holds the pre-bookkeeping sha and the bytes of the files to restore.
- `snapshot_bookkeeping`: records the sha, the work files, the session sidecar and the worker logs. A `git reset --keep` would delete worker logs that the bookkeeping commit newly added, so they are rewritten too.
- `merge_undo_snapshot`: takes the snapshot only for merge mode without a rollup, which keeps finish_task.py at 400 lines.
- `undo_bookkeeping`: checks out the branch (guard for a landing that raised while another branch was checked out), runs `git reset --keep`, rewrites the files, and returns why it failed or `None`.
- `finish_modes._land_reporting_errors`: in merge mode, turns an exception from `land_on_integration` into a failure, so the undo runs. auto and pr re-raise as before. Kept as a separate helper so `apply_on_complete_mode` stays within 80 lines.
- `merge_landing_failed` `undo=` parameter and its three message branches: the re-run text after a successful undo, after a failed undo, and for the unchanged retry.
- `sys.stdout.flush()` in `merge_landing_failed`, the auto error, `refuse_unless_finish_tip`, and per line in `_run_streaming`: needed for the A1 ordering.
- `apply_on_complete_mode` `undo=` parameter and the `undo=undo` wiring in `finish_task._finish_locked`: the A2 hook.
- `tests/test_finish_merge_failure_undo.py::test_push_rejected_by_remote_reports_last_and_undoes`: A4(a).
- `tests/test_finish_merge_failure_undo.py::test_landing_exception_reports_last_and_undoes`: A4(b), with a `mock.patch.object` on `finish_modes.land_on_integration` inside the subprocess.
- `tests/test_finish_merge_failure_undo.py::test_undo_failure_names_the_reset`: the A2 undo-failure message.
- The `monkeypatch.setattr(finish_task, "merge_undo_snapshot", ...)` in the two retry tests: simulates a branch finished before this change (A3).
- `tests/test_finish_merge_mode.py`: renamed `_merge_mode_finish_repo` to the public `merge_mode_finish_repo` and updated its one existing caller, so the new test module never imports an underscore-prefixed name (coordinator precheck). All assertions are unchanged.
