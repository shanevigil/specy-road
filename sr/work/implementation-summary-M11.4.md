# Implementation summary: M11.4 — max_workers counts live workers across checkouts and applies to resumes

Branch `feature/rm-max-workers-global`, base `be6a6a63` (WIP merged in at `2e0f5d12` to widen the touch zones).

## Round 2 (after gpt-6.1-sol's block on A1)

The first round found other clones' workers through claims on the integration branch's registry. It filtered them by "no local branch of that name" and "owner equals my `user.name`". Both are heuristics, and the review showed each one skipping a live foreign worker. Per the maintainer's decision, those heuristics are replaced by an explicit, ref-based lease.

- **Lease ref** (`specy_road/worker_lease.py`, new section below the human handoff/reclaim lease): `refs/specy-road/leases/<checkout-id>/<worker-id>` on the integration remote (`remote` in `git-workflow.yaml`). Its value is a parentless commit on the empty tree whose message names the worker, so a push uploads nothing else.
- **Checkout id:** a uuid written once (`O_EXCL`) to `<git-common-dir>/specy-road-checkout-id`. Linked worktrees share it with the main checkout, just as they share `work/.workers/`. A clone has its own.
- **Count:** the active records in this checkout's `work/.workers/` other than the resumed worker, plus lease refs from `git ls-remote <remote> 'refs/specy-road/leases/*'` whose checkout id differs. Branch names and owners play no part.
- **Launch** (`delegate`): it reads the foreign leases once before the lock, since that is a network call, and uses them for both slot checks. After `create_record` and before `spawn`, `acquire_lease` pushes the lease and counts again. If the recount is over the limit, the lease is deleted, the record goes `failed` with an `error` event, and the launch is refused. Two checkouts launching at once therefore cannot both exceed the limit, though both may be refused.
- **Resume** (`message`/`resume`): the local slot check as before, then `acquire_lease` just before the `message` event and the spawn. A refusal on an `idle`/`completed` worker keeps its existing lease (`new=False`). A `failed` worker's new lease is withdrawn on refusal (`new=True`).
- **Lifetime:** the lease follows the record's active state. It is kept on `idle`, `completed` and `handed_off`, and deleted on `failed` and `terminated`:
  - `worker_runner._exit_state` releases it when the state is `failed`.
  - `worker_runner._refuse` releases it when spawn is refused.
  - The wrapper releases it when it cannot start the harness.
  - `worker_process.wrapper_gone` (a dead wrapper marked `failed`) releases it, via a lazy import because `worker_lease` imports `worker_process`.
  - `worker_ops.terminate` releases it after the lock.
  - `worker_ops._launch_locked` releases it when the wrapper cannot start.
- **sync** (`worker_reconcile.sync`): after the lock, `release_stale_leases` deletes this checkout's lease refs whose worker is no longer active here.
- **No remote / unreachable:** a repository without the remote configured pushes and reads nothing, which covers every existing test fixture. When the remote fails (`ls-remote` non-zero, or a lease push fails), one warning goes to stderr ("max_workers counted this checkout's workers only, not other checkouts'"). The URL is remembered as offline for the rest of the process, so no further network calls are tried, and the command goes on.
- **Removed:** `worker_ops.claimed_elsewhere` and its registry, owner and branch filters, and the test `test_a_claim_by_another_user_is_not_counted`, which asserted the rejected behaviour.
- **Docs** (`docs/orchestration-workers.md`): the "What `max_workers` counts" paragraph is rewritten for the lease. It covers the ref name, the checkout id, the recount after push, the lifetime, the sync sweep, offline behaviour and the network cost. The file stays at 398 lines.

## Weight of pushing on every launch

A launch costs one `ls-remote`, one push and one more `ls-remote`. A resume costs one push and one `ls-remote`, a close one push, and `sync` one `ls-remote`. Each call has a 20 s timeout. That seemed acceptable next to pickup's own push, so I didn't propose an alternative.

Two costs remain:
- `message`/`resume` run entirely under the workers lock, as before, so their push and `ls-remote` run under it too. The same is true of the release in `wrapper_gone`, which is called from sweeps that hold the lock. `delegate`'s first read and `terminate`'s release run outside it.
- A lease that could not be deleted (offline) over-counts in other checkouts until this checkout's next `sync`. That is the safe direction.

## Not new: `specy_road/worker_lease.py`

The touch zone named `worker_lease.py` as new, but that module already exists: it holds the human `handoff`/`reclaim` lease. The slot lease is a separate section in the same file (now 282 lines), and the module docstring says so. No path outside the touch zones was needed, and the registry schema and `validate` are unchanged.

## Acceptance

- **A1:** `delegate`, `message` and `resume` refuse a launch past `max_workers`. The count covers the main checkout and its linked worktrees (shared records) plus every other checkout's lease refs, whatever local branches exist and whoever owns the claim.
- **A2:** the docs paragraph above.
- **A3:** `tests/test_worker_max_workers_global.py` covers:
  - a resume refused at the limit: a lowered limit, a foreign lease on a branch that also exists locally, and leases from another owner;
  - two checkouts sharing one limit (`delegate` refused by the clone's lease);
  - the recount after push;
  - the lease's lifetime and the sync sweep;
  - the unreachable-remote warning.

## Verification (round 2)

As instructed, I ran only the touched test file. I did not re-run the other worker suites after this round.

- `python -m pytest tests/test_worker_max_workers_global.py -q -p no:cacheprovider`: 11 passed in 13.96s.
- `specy-road file-limits`: OK.
- `ruff check` on the six changed Python files: all checks passed.

## Added

- `worker_lease.checkout_id`: the stable per-repository id, shared by linked worktrees (a uuid in the git common dir).
- `worker_lease.LEASES`, `LEASE_TIMEOUT`: the ref namespace and a bound on every lease network call.
- `worker_lease._OFFLINE`, `_remote`, `_offline`: no remote means no leases; a failed remote warns once per process and is not retried, so offline work is not slowed.
- `worker_lease._lease_refs`, `foreign_leases`: read lease refs; count those of other checkouts.
- `worker_lease.max_workers`: the policy limit, raising a `WorkerError` on an unreadable config rather than a `KeyError`.
- `worker_lease.slot_error`: the one refusal message, shared by the local and lease checks.
- `worker_lease.acquire_lease(…, new=)`: push, then recount, so simultaneous launches never exceed the limit. `new` decides whether a refusal withdraws the lease.
- `worker_lease.release_lease`: delete lease refs, best effort.
- `worker_lease.release_stale_leases`: sync's sweep of this checkout's leases with no active local worker.
- `worker_ops._slot_or_existing(…, own=, foreign=)`: a resumed worker leaves itself out; `foreign` is the lease list read outside the lock.
- `worker_ops._launch_locked` lease guard: refused acquire → `error` event, `failed`, re-raise; release when the wrapper cannot start.
- `worker_ops._send`: `acquire_lease` before the message event and the spawn (A1 for resume).
- `worker_ops.terminate`: release after the lock.
- `worker_runner`: release on `_refuse`, on harness-start failure, and in `_exit_state` for `failed`.
- `worker_process.wrapper_gone`: release when a dead wrapper is marked `failed`.
- `worker_reconcile.sync`: `release_stale_leases` after the lock.
- File-limit housekeeping in `worker_ops.py` (round 1, no behaviour change): removed the unused `_now`, extra blank lines and a docstring line; `adopt`'s inner `fn` became an equivalent `mutate` lambda.
- Test `test_a_linked_worktree_shares_the_checkout_id_and_a_clone_does_not`: the checkout id's scope.
- Test `test_two_checkouts_share_one_limit`: A3, `delegate` refused by a clone's lease, no record left.
- Test `test_a_foreign_lease_counts_when_its_branch_also_exists_here`: review P1 (1), through public `resume`.
- Test `test_leases_from_another_owner_count`: review P1 (2), through public `message`, with no message event recorded.
- Test `test_a_lease_pushed_second_is_refused_and_withdrawn`: the recount after push, and the refused lease is deleted.
- Test `test_the_lease_follows_the_record`: an idle worker keeps its lease; `terminate` deletes it.
- Test `test_sync_releases_a_dead_or_stale_workers_lease`: the dead-wrapper release and the stale sweep.
- Test `test_an_unreachable_remote_counts_local_workers_and_warns_once`: the offline path, with exactly one warning and the launch going ahead.
- Tests kept from round 1: linked worktree counted, idle resume in its own slot, resume refused when local workers fill a lowered limit.
- Test helpers `_remote_and_clone`, `_leases`, `_idle`, `_foreign_worker`: a bare integration remote with a second clone, lease listing, an idle record, and a foreign worker holding its lease.
- Mocks: none; the remote is a real bare repository in `tmp_path`.
