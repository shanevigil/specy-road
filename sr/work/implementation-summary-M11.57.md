# Implementation summary — M11.57 `completed-worker-frees-slot`

Base: `8285937a` with `origin/WIP/improvements-0-3-1` merged in (`54aaaff7`, which updated the touch zones). Implementation commit: `c3518c98`.

## What changed

- **A1: slot count.** `worker_ops_slots._slot_or_existing` (used by delegate, message and resume) and `worker_lease.acquire_lease` (the recount after a lease push) now count only `holding_slots(...)`. An `idle` or `completed` worker no longer counts when either:
  - its leaf is Complete in the roadmap graph at the integration branch (`refs/heads/<ib>`, else `refs/remotes/<remote>/<ib>`, read with `load_roadmap_nodes_at_ref`), or
  - the claim it was delegated under (`node_id` and `rec.branch`) is gone from this checkout's registry.

  A completed or idle worker on an unfinished, still-claimed leaf keeps its slot. Running, starting and handed-off workers always count. `worker_lease.sync_leases` now also deletes the lease ref of a worker that stopped counting, and pushes refs only for workers that still count, so other checkouts stop counting it too.
- **A2: refusal text.** `worker_lease.slot_error` now takes the counted records and keeps its old prefix (`N workers active[ (and … leased by other checkouts …)], policy max_workers is L; `). The rest comes from `worker_orphans.slot_breakdown`, for example `2 running: w-0001, w-0002; 1 completed: w-0003; `specy-road worker terminate w-0003` frees it, or wait for a running one to finish or raise the limit`.
- **A3: orphans.**
  - `worker_orphans.orphans()` names each idle or completed worker whose leaf is Complete, whose claim is gone, or whose worktree directory no longer exists, with the reason. A worker whose worktree is gone is orphaned but keeps its slot, because its leaf is still open.
  - `worker list` marks each such worker `orphaned: <why>` (`orphaned` in `--json`, `null` otherwise). `worker sync` lists every orphan after the events, whether or not it has new events (`orphaned` in `--json`).
  - `worker terminate --orphaned` ends them all under one lock, makes one lease release afterwards, and prints each worker with its reason.
  - `finish-this-task` calls `end_finished_workers` after its bookkeeping commit. This terminates the finished leaf's own idle and completed workers through `_terminate_locked`, which records a `terminated` event for each. A running worker is left alone. This step never fails the finish: on an error it prints a `[warn]` line.
- **Docs.** `docs/orchestration-workers.md` covers this in the state row, the "What `max_workers` counts" paragraph, a new **Orphaned workers** paragraph, the `list`, `sync` and `terminate` rows, and the finish note in "Working alongside sessions". The file is now at 400/400 lines; the new text went into existing lines plus one paragraph.

## Decisions

- **Orphan status is not stored.** The `flags` and event `type` enums in `specy_road/schemas/worker-record.schema.json` and `worker-event.schema.json` are outside the touch zones, and a cause can come and go (a leaf reopened, a claim taken again). So orphan status is worked out again on every list, sync, launch and resume. The `terminated` event that finish and `--orphaned` record keeps `_terminate_locked`'s generic summary ("terminated by the coordinator"); the reason is printed to the console instead. `worker_ops_lifecycle.py` is outside the zones, so I did not add a reason parameter there.
- **"No longer claimed" requires `rec.branch`.** Delegate and adopt always set it. A record without a branch (only hand-made records in tests) is never treated as unclaimed, because there is no claim to compare against.
- **Unreadable registry.** If the registry is missing or unreadable, `claims` is `None`, so no worker is ever judged unclaimed because of a read failure.
- **The claim check reads this checkout's registry,** the same one `delegate` requires the claim in. Complete is read from the integration branch refs, not from the working tree.
- **`worker_reconcile.py` is unchanged.** `sync()` still returns its delta list, so `sync --wait`'s truthiness check keeps working. The orphan lines are added in the CLI from `orphans()`.
- **Locking in `_end`.** `_end` reads the records before it takes the workers lock, so a finish in a checkout with no workers does not create `work/.workers/`. `tests/test_prerelease_s5.py` caught this: it asserts a clean `git status` after finish.

## Touch zones (final)

Changed: `specy_road/worker_orphans.py` (new), `specy_road/worker_ops_slots.py`, `specy_road/worker_lease.py`, `specy_road/bundled_scripts/worker_cli.py` (now 399/400 lines), `specy_road/bundled_scripts/finish_task.py`, `docs/orchestration-workers.md`, `tests/test_worker_orphans.py` (new).

In the zones but not changed: `specy_road/worker_ops.py`, `specy_road/worker_state.py` (400/400), `specy_road/worker_reconcile.py`.

`worker_cli.py` was at 397 lines, so the CLI code for this leaf (the `terminate` parser and its `--orphaned` path, `list_view`, `orphan_lines`) lives in `worker_orphans.py`. `worker_cli.py` only calls it.

## Verification

- `pytest -n auto -q tests/test_worker_*.py tests/test_prerelease_workers.py tests/test_gui_app_workers.py tests/test_finish*.py tests/test_branch_cleanup.py tests/test_cli_loop_base_dependencies.py tests/test_integrity_gate.py tests/test_human_acceptance.py tests/test_mark_implementation_reviewed_gate.py tests/test_prerelease_s5.py tests/test_project_layouts_outside.py tests/test_prerelease_s2.py tests/test_review_round4_sol.py tests/test_review_round4_sol_b.py tests/test_review_round5.py tests/test_review_round6_ops.py tests/test_review_round6_runner.py tests/test_roster_source.py tests/test_runtime_dirs_not_dirty.py tests/test_rollup_branch_cleanup.py tests/test_grind_session*.py`: 666 passed. In an earlier run under load, `test_worker_cli.py::test_sync_wait_ends_on_an_event_or_times_out_with_exit_2` failed once; it passed alone and in the final run. That test waits on a timeout.
- `specy-road file-limits`: OK.
- `ruff check` on the changed Python files: clean. A repo-wide `ruff check specy_road` still reports one existing C901 in `review_packet_uncommitted_refs.py`, which this leaf did not touch.
- `python3 scripts/check_test_private_imports.py`: 0 new. It also reports one stale baseline entry that this change did not cause.
- Red/green: with `worker_ops_slots.py` restored to the base version, both "frees its slot" tests fail. With the change, they pass.

## Added

- `specy_road/worker_orphans.py`: new module, because `worker_state.py` (400) and `worker_lease.py` (388) are at the line cap.
- `worker_orphans.HELD_STATES` / `RUNNING_STATES`: which states can be freed (idle, completed) and which group as "running" in the refusal.
- `worker_orphans._HINT`: the one `terminate --orphaned` hint line shared by `list` and `sync`.
- `worker_orphans._Leaves`: reads registry claims and integration-branch Complete ids lazily, at most once per call, so a check with no held workers costs no git calls.
- `worker_orphans._Leaves.claims` returns `None` on an unreadable registry: guard so a read failure never frees a slot.
- `worker_orphans._Leaves.complete`: checks the local integration branch, else the remote-tracking one, so a clone lane whose local branch is stale still sees the landing.
- `worker_orphans._cause`: one place that decides orphaned or not, why, and whether that frees the slot. The worktree-gone cause does not free it (A1 frees only Complete or unclaimed leaves).
- The `rec.branch` guard in `_cause`: a record that never recorded a claim is not judged unclaimed.
- `worker_orphans.holding_slots`: the slot count (A1), used by `_slot_or_existing`, `acquire_lease` and `sync_leases`.
- `worker_orphans.orphans`: orphan marks for list, sync and `--orphaned` (A3).
- `worker_orphans.slot_breakdown`: the running/held split and the terminate hint in the refusal (A2).
- `worker_orphans._end`: shared locked bulk terminate with one lease release, plus a read-before-lock guard so no `work/.workers/` is created when nothing is ended.
- `worker_orphans.terminate_orphaned`: `worker terminate --orphaned` (A3).
- `worker_orphans.end_finished_workers`: finish's cleanup of its own leaf's workers (A3).
- `worker_orphans.orphan_lines`, `list_view`, `add_terminate`: CLI code kept out of `worker_cli.py`, which is at the cap. `add_terminate` makes `W` optional and refuses neither/both and `--orphaned --op-id` (argparse exit 2).
- `worker_lease.slot_error` now takes records instead of a count, with a docstring, so it can name running and held workers apart.
- `worker_lease.sync_leases` now releases a freed worker's lease and pushes leases only for workers that count. Removed `_closed`, which only this function used and which is now covered by the counted set.
- `worker_ops_slots._slot_or_existing`: an early return when `foreign is None`, then the count through `holding_slots`.
- `finish_task._end_leaf_workers`: best-effort call after the bookkeeping commit. It prints each terminated worker; a `WorkerError` or `OSError` prints `[warn]` and never fails the finish.
- `worker_cli.py`: `cmd_list` goes through `list_view`; `cmd_sync` adds `orphaned` to its JSON and lines; the `terminate` parser comes from `add_terminate`.
- `tests/test_worker_orphans.py`, 12 tests (14 cases):
  - Complete-on-integration frees the slot (resume succeeds at `max_workers=1`).
  - Claim gone frees the slot.
  - An unfinished leaf holds the slot, and the CLI refusal text is checked.
  - A running worker is never orphaned.
  - Worktree gone: orphaned but still holding the slot.
  - The refusal names running and held workers apart, with and without foreign leases.
  - `list` and `sync` mark orphans (text and `--json`, and `sync` with no new events).
  - `terminate --orphaned` ends only the orphans, records a `terminated` event, and a second run says "No orphaned workers."
  - `terminate` argument errors (3 parametrised cases).
  - Single-worker `terminate` still works.
  - `finish-this-task` terminates the leaf's idle and completed workers, leaving a running one and another leaf's worker.
  - With no workers, `end_finished_workers` ends nothing and creates no `work/.workers/`.
- Test helpers `_worker`, `_claim`, `_complete_on_dev`, `_three`: fixtures for held records, an extra claim, a leaf Complete on `dev`, and the two-orphans-plus-one-kept setup. No mocks were added.
