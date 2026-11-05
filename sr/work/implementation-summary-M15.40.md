# Implementation summary: M15.40

finish-this-task: a failed merge landing reports after the land check output and undoes its bookkeeping commit.

## What changed

- **A1 (output order).** Took the "flush stdout before each stderr message" option rather than line-buffering in `finish_task.main`, because `specy_road/bundled_scripts/finish_task.py` sits at the 400-line cap in `sr/constraints/file-limits.yaml` (the effective cap for this checkout). `finish_land_check._run_streaming` flushes after each line it copies. `merge_landing_failed` (used by both the merge path and the retry path), the `auto` fallback error, and `refuse_unless_finish_tip` flush stdout before they write to stderr. A pipe shared by stdout and stderr now ends with the outcome. **Round 2:** `landing_error_line` (finish_modes) prints a multi-line reason in full to stdout first, then one `error: could not land merge to <ib>: <reason>` line with the reason joined by ` / ` (`one_line`). It serves the merge, retry and auto paths. **Round 3:** on success, `report_landed` (finish_modes) runs every step that follows a landing first (session-file removal and `--delete-branch`'s checkout and deletes, whose `[warn]` now flushes stdout first). It then flushes both streams and prints `[ok] <outcome>` last. All three success exits use it: `apply_on_complete_mode` (merge and auto), `retry_merge_landing`'s landing, and its "already merged" exit. The outcome is the final line under any option.
- **A2 (undo).** New module `specy_road/finish_bookkeeping_undo.py`. Before the bookkeeping phase, finish records the HEAD sha and the bytes of the files that phase removes or archives: `work/brief-`, `prompt-` and `implementation-summary-<ID>.md`, the on_complete session sidecar, and this leaf's `work/worker-logs/<ID>/`. It takes this snapshot only in merge mode and not for a rollup (`merge_undo_snapshot`). If `land_on_integration` fails or raises in merge mode, `apply_on_complete_mode` calls `undo_bookkeeping`, which checks out the feature branch if needed, runs `git reset --keep <pre-sha>` and writes the files back. `merge_landing_failed(..., undo=(sha, failure|None))` then names a plain `specy-road finish-this-task`. It adds `--on-complete merge --override-on-complete` only when merge was an override of the configured mode, because a plain re-run would otherwise use the configured mode. **Round 2:** the snapshot now covers exactly what the cleanup deletes or moves, through one function, `finish_work_artifacts.cleanup_paths`. It is built on `removal_target`, which `remove_work_file` and the sidecar cleanup now share. So a symlinked brief's in-repo target, which cleanup deletes, is snapshotted. Entries record a symlink as a link and anything else as bytes. `undo_bookkeeping` returns an `UndoOutcome`: the checkout or reset error, and the files it could not write back, each saved to a temp copy. It writes back every path `pre_sha` does not track, whichever step failed, and leaves tracked paths to the reset. `undo_report` is the one place that turns the outcome into text: success, restore failure after a successful reset (branch and claim back, file named with its saved copy, no claim that the commit remains), or checkout/reset failure (commit still on the branch, which untracked files are back, then `git [checkout <b> &&] reset --keep <sha>` followed by the re-run).
- **A3.** `retry_merge_landing` is unchanged and still calls `merge_landing_failed` without `undo`, so its message ("bookkeeping is already committed, retries only the landing") is the same. auto and pr pass no snapshot and keep their commit. Step 9 of `docs/dev-workflow.md` now describes the undo, the plain re-run, the undo-failure reset and the retry for branches an earlier finish left committed.
- **A4.** `tests/test_finish_merge_failure_undo.py` runs finish in a sandbox with a bare remote and a passing `land_check_cmd`, with stderr merged into stdout. Case (a) uses a pre-receive hook. Case (b) runs finish through `python -c` with `specy_road.finish_modes.land_on_integration` patched to run the real land check and then raise `OSError`. Each case asserts exit 1, finish's `error: could not land merge to dev:` line after the check output with the reason in it (`remote rejected` / `OSError: simulated landing crash`), the branch tip equal to its pre-finish sha, a clean tree, the registry claim held, and the brief and summary restored byte for byte (not archived under `work/done/`).

## Touch zones (final)

These are as listed. The new module `specy_road/finish_bookkeeping_undo.py` was already in the zones. No file outside them changed.

## Verification

- `python -m pytest -n 4 -q`: 4910 passed (round 2, after merging origin/WIP/improvements-0-3-1). `ruff check specy_road tests`: clean.
- `specy-road file-limits`: OK.
- Red-green: with the flushes in `finish_modes.py` and `finish_land_check.py` removed, both sandbox tests fail on ordering. With the snapshot disabled (`undo = None`), both fail on the branch tip and registry. Round 2: when `cleanup_paths` stops listing removal targets, `test_symlinked_brief_target_is_restored` fails.

## Existing tests adjusted

- `tests/test_branch_cleanup.py::test_a_retried_landing_deletes_the_branch` and `tests/test_prerelease_s2.py::test_rerunning_finish_retries_a_failed_merge_landing` test the retry of a branch already left on its bookkeeping commit. A2 means a current finish no longer leaves that state. Each test now patches `finish_task.merge_undo_snapshot` to return `None`, which simulates an earlier finish, so the retry path (A3) is still covered with every original assertion unchanged.

**Round 4:** the undo restores exactly the pre-finish working-tree state of every captured path, tracked or not. The snapshot also records `("absent", b"")` for a cleanup path that did not exist. After a successful reset, `undo_bookkeeping` sets every entry to its captured state (bytes, link, or absent), so a locally modified tracked brief, prompt or summary gets its modified bytes back, not HEAD's. When the checkout or reset fails, writing a tracked path would block the `git reset --keep` the report names. So only untracked paths are written, and a tracked path whose captured bytes differ from `pre_sha` (`_differs_from`, via `git hash-object`) is saved to a temp copy. The report then names the copy and says to put it back after the reset.

## Probes

Class 1, multi-line text on an outcome `error:` line:
- `merge_landing_failed` (merge path and the `retry_merge_landing` path): one line via `landing_error_line`, full text on stdout first. Fixed; tested.
- `auto` fallback error in `apply_on_complete_mode`: same helper. Fixed.
- Undo error details (git checkout/reset output, OSError text, file lists) in `undo_report`: `one_line`. Fixed; tested.
- `refuse_unless_finish_tip`: fixed one-line text. No change needed.
- `merge_landing_preflight`: exits before the bookkeeping commit and the land check, so it is outside A1's "after a passing land check". Left as is.

Class 2, the snapshot not matching what cleanup actually removes:
- brief/prompt/summary via `remove_work_file` (resolves symlinks): now one `removal_target` shared by delete and snapshot. Fixed; regression test with an ignored brief symlink to untracked `notes/brief.md`.
- Session sidecar via `cleanup_session_sidecar`: same `_sidecar_rel` + `removal_target` path. Fixed.
- Tracked summary archived with `shutil.move` (moves a link as a link): `cleanup_paths` lists the path itself; the snapshot records a link as a link, and the reset restores it. Covered.
- `_keep_untracked_summary`: copies only, removes nothing. No change needed.
- Worker logs, added by the commit and deleted by the reset: symlinks are now recorded as links (`os.readlink`) and recreated, not skipped. Fixed.
- `work/pr-body-*`: not written or removed in merge mode. No change needed.

Class 3, an undo message that claims a state the failed step did not produce:
- Checkout failure, reset failure, restore failure after reset, and success are each a distinct `undo_report` branch. Tests cover reset failure (real `git reset --keep` refusal) and restore failure (real `OSError`, saved copy checked byte for byte).
- Untracked bytes are written back even when the git step fails. Because only paths `pre_sha` does not track are written, the later `git reset --keep` the message names cannot conflict with them.

Class 4 (round 3), output printed after the outcome line on a successful landing:
- `apply_on_complete_mode` success (merge, and auto when its merge lands): `--delete-branch` messages and session removal now come before the outcome. Fixed; tested with `[]`, `--delete-branch`, `--delete-branch --push --no-cleanup-work` and `--delete-branch --land-check-cmd`.
- `retry_merge_landing` landing: same function. Fixed; tested (last line is `[ok] merged ...`).
- `retry_merge_landing` "already merged" exit with `--delete-branch`: same function. Fixed; tested (last line is `[ok] ... is already merged into dev on origin`).
- `delete_landed_branch`'s `[warn]` on stderr: stdout is flushed before it, so a shared pipe keeps the order. Fixed.
- `finish_task._finish_locked` after `apply_on_complete_mode`: nothing runs after it (`_end_leaf_workers` and the bookkeeping push run before the landing). No change needed.
- Options that print before the landing (`--push`, `--no-cleanup-work`, `--land-check-cmd`): covered by the parametrized test. `--allow-*` and `--override-on-complete` print only in gates before the bookkeeping commit. No change needed.
- `finish_milestone_rollout`'s own `delete_landed_branch` call: the milestone rollup path is out of scope (A5). Left as is.

Class 5 (round 4), a captured path whose pre-finish state differs from what the reset produces:
- Tracked brief, prompt and summary edited locally, then a rejected push (successful reset): the edited bytes are restored, unstaged. Fixed; public CLI test `test_locally_modified_tracked_documents_come_back_as_they_were`.
- The same with a failed reset: the edited tracked brief is saved and named, and the report says to put it back after the reset. Fixed; tested.
- A path absent before finish but present after the reset (for example a tracked file the user had deleted locally): it is removed again (`absent` entry). Fixed.
- A path whose kind changed (link vs file): the wrong kind is unlinked before writing. Fixed.
- Untracked work files, symlink targets and worker logs: unchanged behaviour, now on the same "captured state" rule. Existing tests pass.
- The session sidecar: it is in `cleanup_paths`, so the same rule applies. Covered.

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
- Round 2: `finish_work_artifacts.removal_target`, the one resolution of what `remove_work_file` deletes, now shared with the snapshot.
- Round 2: `finish_work_artifacts._sidecar_rel`, the sidecar path shared by cleanup and `cleanup_paths`.
- Round 2: `finish_work_artifacts.cleanup_paths`, the one "what cleanup removes or moves" function the snapshot uses.
- Round 2: `finish_bookkeeping_undo.one_line`, which collapses a reason onto one line for A1.
- Round 2: `UndoOutcome`, which records the step that failed and the files not restored, each with its saved copy.
- Round 2: `_restore`, which recreates a link as a link and a file as bytes. `_save_copy` keeps bytes that could not go back, in a temp dir.
- Round 2: `undo_report`, the one undo report. `finish_modes.landing_error_line` gives the single outcome line, with the full reason on stdout first.
- Round 2: the `pre_sha:./path` check in `undo_bookkeeping`, so only paths `pre_sha` does not track are rewritten. The reset owns the tracked ones, so the named reset never conflicts.
- Round 2 tests: `test_symlinked_brief_target_is_restored`, `test_multiline_reason_is_one_error_line_and_kept_in_full`, `test_reset_failure_keeps_untracked_files_and_names_the_reset`, `test_restore_failure_after_reset_saves_a_copy`, and the `_undo_repo` fixture. They replace `test_undo_failure_names_the_reset`, which used the old tuple API. The end-to-end helper now also asserts that the reason is on the single error line and that only the next-command paragraph follows it.
- Round 3: `finish_modes.report_landed`, the one success reporter that runs post-landing steps first and prints the outcome last, used by all three success exits.
- Round 3: the `sys.stdout.flush()` before `delete_landed_branch`'s stderr `[warn]`, which keeps the order under a shared pipe.
- Round 3 tests: `test_a_landed_finish_prints_its_outcome_last` (parametrized over the options above) and `test_a_retried_landing_prints_its_outcome_last`. The latter uses a `_NO_UNDO` subprocess wrapper that patches `finish_task.merge_undo_snapshot` to `None`, to reproduce a branch an older finish left committed. Red-green: against the round-2 `finish_modes.py`, 4 of the 5 new cases fail; only the no-options case passed before too.
- Round 4: `("absent", b"")` snapshot entries, so a path that did not exist before finish ends absent.
- Round 4: `_restore` unlinks a wrong-kind or should-be-absent entry before writing.
- Round 4: `_differs_from` (`git hash-object` against `pre_sha:./path`) decides which tracked paths to save when the reset failed.
- Round 4: `undo_bookkeeping` writes every entry after a successful reset, not only untracked ones.
- Round 4: the reset-failure report tells the user to put the saved files back after the reset.
- Round 4 tests: `test_locally_modified_tracked_documents_come_back_as_they_were` (public CLI, rejected push) and `test_reset_failure_saves_modified_tracked_documents`. Red-green: both fail against the round-3 `finish_bookkeeping_undo.py`.
