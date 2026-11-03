# Implementation summary — M11.57 `completed-worker-frees-slot`

Base: `8285937a` with `origin/WIP/improvements-0-3-1` merged in (`54aaaff7`, which updated the touch zones).

Commits:
- `c3518c98`: implementation.
- `b8516f50`: fix round 1, Codex Sol F1. Claims are read from the integration branch, not the caller's worktree.
- `90b03081`: fix round 2, Codex Sol F1. One conservative rule replaces the separate Complete and claim checks; a stale Complete ref no longer overrides a reopened leaf.
- `096d5040`: merge of `origin/WIP/improvements-0-3-1` (brings in WIP's new Codex reviewer entries; no behaviour change for this leaf). `finish_task.py`: kept WIP's `pickup_finish_lock` import beside this leaf's imports; `_end_leaf_workers` still runs after the bookkeeping commit, now inside WIP's lock. `docs/orchestration-workers.md`: took WIP's one-line paragraph, with this leaf's finish sentence replacing "`terminate` the idle worker afterwards". `worker_cli.py` auto-merged to 401 lines, so the leaf's two `sync` lines became one call to the new `worker_orphans.with_orphans`, back to 400. After the merge: `tests/test_worker_orphans.py` with `tests/test_worker_cli.py`, 36 passed; WIP's finish and lock tests, 18 passed; file-limits OK.

## What changed

**The rule (round 2).** An `idle` or `completed` worker's leaf is **over** only when, at **every** integration ref that exists (`refs/heads/<ib>` and `refs/remotes/<remote>/<ib>`), both of these hold at that same ref:
- the leaf has no registry claim under any branch;
- the leaf is Complete in that ref's roadmap.

That is how a landed finish leaves it. The worker is kept when:
- no integration ref exists;
- a ref's registry or graph can't be read, or the leaf is missing from a graph;
- the refs disagree, for example a stale `origin/dev` still saying Complete for a leaf reopened on `dev`, or a landing on local `dev` not yet pushed and fetched;
- there is any claim on the leaf.

The caller's working tree is never read. A gone worktree is not a cause on its own; when an orphan's worktree is gone, its reason says so. The rule is `worker_orphans._Leaves.over`, and `_cause` applies it. Three things share it: slot accounting, the `list`/`sync` orphan marks, and `terminate --orphaned`.

- **A1: slot count.** `worker_ops_slots._slot_or_existing` (used by delegate, message and resume) and `worker_lease.acquire_lease` (the recount after a lease push) count only `holding_slots(...)`: every active worker except held ones whose leaf is over. An idle or completed worker on an unfinished, claimed or ambiguous leaf keeps its slot. Running, starting and handed-off workers always count. `worker_lease.sync_leases` deletes the lease ref of a worker that stopped counting and pushes refs only for workers that count.
- **A2: refusal text.** `worker_lease.slot_error` takes the counted records and keeps its old prefix (`N workers active[ (and … leased by other checkouts …)], policy max_workers is L; `). `worker_orphans.slot_breakdown` adds the rest, for example `2 running: w-0001, w-0002; 1 completed: w-0003; `specy-road worker terminate w-0003` frees it, or wait for a running one to finish or raise the limit`.
- **A3: orphans.**
  - `worker list` marks each orphaned worker `orphaned: <why>`, for example `M1.2 is Complete and unclaimed on dev and origin/dev`. In `--json` the field is `orphaned`, `null` otherwise.
  - `worker sync` lists every orphan after the events, whether or not it has new events (`orphaned` in `--json`).
  - `worker terminate --orphaned` ends them all under one lock, makes one lease release afterwards, and prints each with its reason.
  - `finish-this-task` runs `end_finished_workers` after its bookkeeping commit. This terminates the finished leaf's own idle and completed workers through `_terminate_locked`, which records a `terminated` event for each. A running worker is left alone. This step never fails the finish; on an error it prints a `[warn]` line.

  Finish names its own leaf explicitly, so it does not go through the orphan rule: on the leaf's branch, the leaf is not yet Complete on the integration branch.
- **Docs.** `docs/orchestration-workers.md` covers the state row, "What `max_workers` counts", the **Orphaned workers** paragraph (rewritten in round 2 for the rule), the `list`, `sync` and `terminate` rows, and the finish note. The file is at 400/400 lines, with all text in existing lines plus that one paragraph.

## Decisions

- **One rule, every consumer (round 2).** Before, Complete statuses were combined across both refs, and a missing claim on its own was a cause, so the newest view could be outvoted. Now each ref must say "over" by itself, so a stale snapshot can only keep a worker, never free one. The cost: a finished leaf whose landing has reached only the local integration branch keeps its worker until `origin/<branch>` is fetched up to it. Finish's own cleanup covers the normal landing in the meantime.
- **"Missing ref".** Only refs that exist are consulted, and at least one must exist. A repo with no remote-tracking ref for the integration branch is judged by its local branch alone. If neither exists, the worker is kept.
- **The claim check is per node, not per (node, branch).** A claim on the leaf under any branch, such as a re-pickup, keeps the worker, so the earlier `rec.branch` guard is no longer needed.
- **Orphan status is not stored.** The `flags` and event `type` enums in `specy_road/schemas/` are outside the touch zones, and a leaf can be reopened, so the rule runs again on every read. The `terminated` event that finish and `--orphaned` record keeps `_terminate_locked`'s generic summary; the reason is printed instead. `worker_ops_lifecycle.py` is outside the zones.
- **`worker_reconcile.py` is unchanged.** `sync()` still returns its delta list, so `sync --wait`'s truthiness check is intact; the orphan lines are added in the CLI.
- **Locking in `_end`.** `_end` reads the records before it takes the workers lock, so a finish in a checkout with no workers does not create `work/.workers/`. `tests/test_prerelease_s5.py` asserts a clean `git status` after finish.

## Touch zones (final)

Changed: `specy_road/worker_orphans.py` (new), `specy_road/worker_ops_slots.py`, `specy_road/worker_lease.py`, `specy_road/bundled_scripts/worker_cli.py` (399/400), `specy_road/bundled_scripts/finish_task.py`, `docs/orchestration-workers.md` (400/400), `tests/test_worker_orphans.py` (new).

In the zones but not changed: `specy_road/worker_ops.py`, `specy_road/worker_state.py` (400/400), `specy_road/worker_reconcile.py`.

`worker_cli.py` was at 397 lines, so the CLI code for this leaf lives in `worker_orphans.py`, and `worker_cli.py` only calls it.

## Verification (round 2)

- The targeted pytest set: 673 passed. The set is `tests/test_worker_*.py`, `tests/test_prerelease_workers.py`, `tests/test_gui_app_workers.py`, `tests/test_finish*.py`, `tests/test_branch_cleanup.py`, `tests/test_cli_loop_base_dependencies.py`, `tests/test_integrity_gate.py`, `tests/test_human_acceptance.py`, `tests/test_mark_implementation_reviewed_gate.py`, `tests/test_prerelease_s5.py`, `tests/test_project_layouts_outside.py`, `tests/test_prerelease_s2.py`, `tests/test_review_round4_sol.py`, `tests/test_review_round4_sol_b.py`, `tests/test_review_round5.py`, `tests/test_review_round6_ops.py`, `tests/test_review_round6_runner.py`, `tests/test_roster_source.py`, `tests/test_runtime_dirs_not_dirty.py`, `tests/test_rollup_branch_cleanup.py` and `tests/test_grind_session*.py`.
- `pytest -n auto -q tests/test_worker_orphans.py`: 21 passed.
- `specy-road file-limits`: OK. `ruff check` on the changed Python files: clean. A repo-wide `ruff check specy_road` still reports an existing C901 in `review_packet_uncommitted_refs.py`, which this leaf did not touch.
- `python3 scripts/check_test_private_imports.py`: 0 new. It also reports one stale baseline entry that this change did not cause.
- Red/green, round 2: with `worker_orphans.py` at `b8516f50` (the version blocked in round 2), 6 tests fail:
  - both reopened-leaf stale-ref cases (Sol's: stale Complete with the claim still present; and stale Complete and unclaimed);
  - both "either half alone" cases;
  - gone worktree alone;
  - landing not yet on the remote-tracking ref.

  With the fix, they pass.
- Red/green, round 1: with `worker_orphans.py` at `7dea46db`, the two-lane and ambiguous-registry tests fail.
- Red/green, base: with `worker_ops_slots.py` at the base version, the "frees its slot" test fails.
- Earlier, under load, `test_worker_cli.py::test_sync_wait_ends_on_an_event_or_times_out_with_exit_2` failed once. It waits on a timeout, and it passed alone and in every later run.

## Added

- `specy_road/worker_orphans.py`: new module, because `worker_state.py` (400) and `worker_lease.py` are at the line cap.
- `worker_orphans.HELD_STATES` / `RUNNING_STATES`: which states can be freed (idle, completed) and which group as "running" in the refusal.
- `worker_orphans._HINT`: the `terminate --orphaned` hint line shared by `list` and `sync`.
- `worker_orphans._REF_TIMEOUT`: the timeout for one `git show` of a registry, matching finish's 30 s.
- `worker_orphans._Leaves`: reads each integration ref at most once per call, and only when a held worker is judged.
- `_Leaves.refs`: the integration refs that exist (local branch, remote-tracking).
- `_Leaves.views` (round 2): per ref, the claimed node ids and the node statuses, each `None` when unreadable. It replaces round 1's combined `claims` and the original combined `complete`.
- `_Leaves.over` (round 2): the conservative rule. It returns the ref labels only when every ref shows the leaf unclaimed and Complete; otherwise `None`.
- `worker_orphans._cause`: `over` applied to held states, plus the gone-worktree note in the reason.
- `worker_orphans.holding_slots`: the slot count (A1), used by `_slot_or_existing`, `acquire_lease` and `sync_leases`.
- `worker_orphans.orphans`: the orphan marks for `list`, `sync` and `--orphaned` (A3).
- `worker_orphans.slot_breakdown`: the running/held split and the terminate hint (A2).
- `worker_orphans._end`: the shared locked bulk terminate with one lease release, plus a read-before-lock guard.
- `worker_orphans.terminate_orphaned`: `worker terminate --orphaned` (A3).
- `worker_orphans.end_finished_workers`: finish's cleanup of its own leaf's workers (A3).
- `worker_orphans.with_orphans` (merge): `worker sync`'s JSON and lines with every orphan added, one call so `worker_cli.py` stays at 400 lines after WIP's `sync` additions.
- `worker_orphans.orphan_lines`, `list_view`, `add_terminate`: CLI code kept out of `worker_cli.py`, which is at the cap. `add_terminate` makes `W` optional and refuses neither/both and `--orphaned --op-id` (argparse exit 2).
- `worker_lease.slot_error`: takes records, not a count, to name running and held workers apart.
- `worker_lease.sync_leases`: releases a freed worker's lease and pushes only for counted workers. It replaces `_closed`, which only this function used.
- `worker_ops_slots._slot_or_existing`: an early return when `foreign is None`, then the count through `holding_slots`. Its docstring states the round-2 rule.
- `finish_task._end_leaf_workers`: the best-effort call after the bookkeeping commit; `[warn]` on `WorkerError` or `OSError`.
- `worker_cli.py`: `cmd_list` goes through `list_view`; `cmd_sync` adds `orphaned`; the `terminate` parser comes from `add_terminate`.
- `tests/test_worker_orphans.py`, 17 tests (21 cases):
  - A completed worker on a landed leaf frees its slot (resume succeeds at `max_workers=1`).
  - Round 2: either half alone keeps the worker (claim gone but not Complete; Complete but still claimed). 2 cases, checked through `resume` refusal and `orphans`.
  - An unfinished claimed leaf holds its slot, and the CLI refusal text is checked.
  - A running worker on a landed leaf still holds its slot.
  - Round 2: a gone worktree alone keeps the worker.
  - Round 2, Sol's regression: a reopened, still-claimed leaf against a stale Complete `origin/dev`, in two variants (stale ref still claimed, Sol's case; stale ref unclaimed). In both, the worker stays unorphaned in `worker list --json`, is counted by `holding_slots` and by the `resume` refusal, and survives `worker terminate --orphaned`.
  - Round 2: a landing on `dev` not yet on `origin/dev` keeps the worker. Once `origin/dev` catches up, it is orphaned on both refs.
  - Round 1: two linked worktrees with differing registry snapshots. The worker is kept while the claim is live. After the leaf really lands on `dev`, `terminate --orphaned` from the worktree whose snapshot still shows the claim ends it, so legitimate cleanup works.
  - An unreadable integration registry keeps the worker, as does no integration branch at all.
  - The refusal names running and held workers apart, with and without foreign leases.
  - `list` and `sync` mark orphans (text, `--json`, and `sync` with no new events). One orphan has a gone worktree, and its reason says so.
  - `terminate --orphaned` ends only the orphans and records `terminated`; a second run says "No orphaned workers."
  - `terminate` argument errors (3 cases).
  - Single-worker `terminate` still works.
  - `finish-this-task` terminates its leaf's idle and completed workers, leaving a running one and another leaf's worker.
  - With no workers, `end_finished_workers` ends nothing and creates no `work/.workers/`.
- Test helpers: `_worker`, `_on_dev` (commit an edit on `dev`; skips an edit that changes nothing), `_registry`, `_claim` / `_unclaim` (on `dev`, as pickup and prune do), `_status_on_dev` / `_complete_on_dev` (round 2: set a node's status on `dev`, adding the node if absent), `_land` (round 2: Complete plus unclaim, as a landed finish leaves it), `_stale_origin` (round 2: pin `refs/remotes/origin/dev` with `git update-ref`), and `_three`. No mocks.
