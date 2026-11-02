# Implementation summary: M11.4 — max_workers counts live workers across checkouts and applies to resumes

Branch `feature/rm-max-workers-global`, base `be6a6a63`. WIP was merged in at `2e0f5d12` and `9a6dc334` to widen the touch zones; the second merge added `specy_road/bundled_scripts/worker_cli.py`.

## Round 8 (gpt-6.1-sol block on A1: failed-state cleanup raced a resume)

WIP was merged first (`53a47d35`). `--offline` is unchanged from round 7.

- **The race:** on a nonzero harness exit, `worker_runner._exit_state` wrote `failed` (and cleared the pids) in one locked `mutate`, then deleted the lease after unlocking. The harness-start failure path did the same with `set_state` and then `release_lease`. A `resume` in that gap saw `failed` with a session, pushed the same lease ref under the lock, and spawned; the old cleanup then deleted that ref, so other clones stopped counting the resumed worker.
- **The fix:** each place that publishes `failed` now writes it and releases the lease inside one `workers_lock` section: `_exit_state` (nonzero exit), the harness-start `OSError` path, `_refuse` (spawn refusal, already under the caller's lock, re-entered to make the pairing explicit) and `worker_process.wrapper_gone` (dead-wrapper close). `resume` acquires under the same lock, so it sees `failed` only once the old lease is gone, and its own lease is never deleted by the old cleanup. `terminate` still releases after its lock: a `terminated` record cannot be resumed.
- **Regression** (`tests/test_worker_lease_races.py`, new file, because `test_worker_max_workers_global.py` would have gone past the 400-line limit): `test_a_failed_turns_cleanup_cannot_delete_the_lease_of_a_resume_that_overlaps_it`, parametrized as `nonzero-exit` (a harness that exits 1) and `harness-start-failure` (a missing binary). It runs the wrapper body, the public `worker_runner.run`, in-process. `worker_runner.release_lease` is wrapped to start `ops.resume` on another thread during the old cleanup and wait up to 1 s for it. Afterwards the resumed worker is idle, its lease is on the remote, and `delegate` in a second clone at `max_workers: 1` is refused. With `worker_runner.py` reverted to the round-7 commit, both cases fail; with the fix, both pass.
- **Docs:** one clause in the "What `max_workers` counts" paragraph says `failed` and its lease deletion are one locked step (398 lines).
- **Verification:**
  - `.conda/bin/pytest tests/test_worker_max_workers_global.py tests/test_worker_lease_races.py tests/test_lean_gates.py -q -p no:cacheprovider` gave 41 passed, 2 skipped. `test_lean_gates.py` was included for the private-import gate.
  - `.conda/bin/ruff check` passed on `worker_runner.py`, `worker_process.py` and both test files.
  - `.conda/bin/specy-road file-limits` passed.

## Round 7 (A1 amended on WIP, 38ea226f)

WIP was merged (`97664017`), which brings in the amended A1. Under it, `--offline` is the explicit local-only escape: it counts this checkout's workers plus the lease refs last fetched, neither fetches nor pushes, and warns that the global limit was not verified. The online count and refusal, and round 6's checkout-id rewrite, are unchanged.

- **Warning** (`worker_lease._warn_offline`): it now reads "warning: --offline: the global max_workers limit was not verified; counted this checkout's workers and the lease refs last fetched from <remote>, and pushed no lease". It is still printed once per remote per process. The `foreign_leases` docstring says the same.
- **Behaviour:** unchanged from round 6. `--offline` still refuses at the count it can see (this checkout's workers plus the last-fetched lease refs), because the amended A1 says the count uses those.
- **Docs:** the `--offline` sentence now names it the explicit local-only escape, says it refuses at that count, and says why the limit is not verified: a worker another checkout started after the last fetch is not seen (398 lines).
- **Tests:**
  - New, `test_offline_warns_and_launches_on_a_stale_mirror`: after one online `sync`, the other clone starts a worker. `delegate --offline` at `max_workers: 1` then exits 0 with exactly one "limit was not verified" warning, and pushes no lease.
  - Updated: the warning assertions in `test_an_unreachable_remote_refuses_unless_offline` and `test_offline_still_counts_the_lease_refs_last_fetched`.
- **Verification:** `.conda/bin/pytest tests/test_worker_max_workers_global.py -q -p no:cacheprovider` gave 28 passed. `.conda/bin/ruff check` passed on `worker_lease.py` and the test file. `.conda/bin/specy-road file-limits` passed.

## Round 6 (gpt-5.6-sol-high and gpt-6.1-sol blocks on A1; A1 kept as written)

WIP (`origin/WIP/improvements-0-3-1`) was merged first (`ded2db22`).

- **`--offline` no longer bypasses the limit.** Lease refs are now read by fetching them, with pruning, into a local mirror, `refs/specy-road/known-leases/<remote>/`, rather than by `ls-remote`. Every online `delegate`, `message`, `resume` and `worker sync` refreshes the mirror. `--offline` skips the fetch and the push but still counts the mirror as last fetched, minus this checkout's own refs. That count applies in `delegate`'s pre-check and in `acquire_lease`'s recount, which now also runs offline, for launches and resumes. So an offline turn is refused at the limit like any other, and the warning says other checkouts were counted from the last fetch. An offline refusal withdraws nothing, because nothing was pushed. Limit: a checkout that has never made an online worker call has an empty mirror, so offline it knows of no foreign workers. A plain `git fetch` does not fill the mirror.
- **An empty or unreadable checkout id is rewritten, not refused.** `checkout_id` treats a missing, empty, unreadable or malformed file as uninitialized: no lease can have been pushed under it, so a new id is safe. Such a file is renamed aside; if the renamed file turns out to hold a valid id (a racing caller wrote one in between), it is linked back. A new uuid is then written to a temporary file and hard-linked into place, which never overwrites, so racing callers converge on one id. It makes up to four attempts and refuses the launch if it still has no usable id. That happens when the id path cannot be set aside or written, for example a directory at that path. I used link rather than a plain rename for the final step because rename overwrites, and two racing callers could each return a different id. The round-4 refusal for an empty file is gone, along with its test.
- **Docs:** the "What `max_workers` counts" paragraph now covers the known-leases mirror, the self-healing id and `--offline` keeping the limit (398 lines).
- **Tests:**
  - `test_offline_still_counts_the_lease_refs_last_fetched`: with a foreign worker at `max_workers: 1` and one online `sync`, `delegate`, `resume` and `message` with `--offline` are each refused through the CLI.
  - `test_an_empty_or_unusable_checkout_id_is_rewritten_and_the_limit_holds`, parametrized over an empty file, a newline and a half-written id: `delegate` through the CLI is refused by the foreign lease, and the id is rewritten valid.
  - `test_a_launch_after_an_empty_checkout_id_leases_under_the_new_one`: the launch pushes its lease under the new id.
  - `test_a_checkout_id_that_cannot_be_written_refuses_the_launch`: a non-empty directory at the id path refuses `delegate` with no record.
  - Updated: the offline warning text, and the sweep-race hook, which now matches the lease fetch instead of `ls-remote`.
- **Verification:** `.conda/bin/pytest tests/test_worker_max_workers_global.py -q -p no:cacheprovider` gave 27 passed. `.conda/bin/ruff check` passed on `worker_lease.py` and the test file. `.conda/bin/specy-road file-limits` passed.

## Round 5 (after gpt-5.6-sol-high's block on A1)

- **R1, an adopted worker was invisible to other clones:** `worker adopt` created an active record but pushed no lease, so another clone at `max_workers: 1` could still launch. `adopt` now calls `lease_adopted` right after `create_record`, under the workers lock. That pushes the lease with `acquire_lease(…, count=False)`: no recount, because the adopted session already runs and refusing it would not stop it. If the lease cannot be pushed (rejected, unreachable, or no usable checkout id), the adopt is refused: an `error` event is appended, the record goes `terminated` (nothing is signalled; the lease is observe-only), and the error is raised. So an adopted worker is never active here without being visible elsewhere. `adopt` has no `--offline`.
- **Every other active source:** I checked the remaining ways a record becomes active. `delegate` and `message`/`resume` push in `acquire_lease`. `handoff` refuses closed records, and `reclaim` returns a handed-off one to `idle`, so both keep the lease they already had. That leaves records with no lease: those registered before leases existed, launched `--offline`, or whose push failed after an offline turn. `worker sync` now pushes those too. `release_stale_leases` became `sync_leases`: under the same workers lock as its deletes, it pushes a lease (best effort, no recount) for each active record with no ref in the remote read, and returns `(released, pushed)`. `worker_reconcile.sync` calls it in place of `release_stale_leases`.
- **R2, a retry failed while the remote was down:** `delegate` read the remote before looking for an existing local worker, so an idempotent retry failed during an outage. It now takes the lock and returns the leaf's existing worker first, with no network call: `_slot_or_existing(…, foreign=None)` looks for the leaf's worker and counts nothing. Only then does it read the foreign leases and run the counted check. The re-check after the prompt build and `acquire_lease`'s post-push recount are unchanged, so a real launch still needs the global count. `_send` now passes `foreign=[]` explicitly to keep its local cap; its foreign count is still `acquire_lease`'s recount.
- **Refactor:** `_push_lease` (the empty-tree commit plus the push) is split out of `acquire_lease`, so `sync_leases` can reuse it. `delegate`'s docstring was reflowed and its two existing-worker returns folded into `if existing := …`, to keep `worker_ops.py` at 398 lines.
- **Docs:** the "What `max_workers` counts" paragraph now covers adopt's lease and refusal, the offline retry, `sync` pushing missing leases, and `--offline` workers becoming visible at the next `sync` that reaches the remote (398 lines).

## Round 4 (after gpt-6.1-sol's third block on A1)

- **P1, a missing or empty checkout id bypassed the leases:** `checkout_id` returned `None` for an empty id file, and every lease call treated `None` like "no remote", so it counted no foreign leases and pushed none. It now returns a valid id or raises a `WorkerError`. Once the integration remote is configured, `foreign_leases` and `acquire_lease` call it unconditionally, so `delegate` (before any record), `message` and `resume` (before the `message` event and the spawn) are refused. `--offline` returns before the id is read, as it reads and pushes no lease.
- **Atomic creation:** the uuid is written to a uniquely named temporary file beside the id file, then `os.link`ed into place, and the temporary file is removed in `finally`. The id file therefore never exists half-written: concurrent first callers get `FileExistsError` and read the winner's id, and an interrupted call leaves no id file, so the next call creates one. A file that exists but does not hold 32 hex digits (an older toolkit's interrupted `O_EXCL`-then-write, or a hand edit) is refused, not replaced, because which id other checkouts saw is unknown. The error names the file and says to remove it; the next `delegate`, `message` or `resume` then writes a new one. A filesystem that cannot hard-link refuses with that error rather than falling back to a non-atomic write.
- **Best-effort paths:** `release_lease` and `release_stale_leases` (`sync`; `sync_leases` from round 5) return quietly without a usable id, because this checkout pushed no lease under one, and they must not fail a wrapper, a terminate or a sync.
- **Docs:** one sentence in the "What `max_workers` counts" paragraph covers the write-then-link creation and the refusal (still 398 lines).

## Round 3 (after gpt-6.1-sol's second block on A1)

- **P1 (1), the stale sweep raced a launch:** `release_stale_leases` read the live records, then the remote, and deleted unlocked. A lease pushed in between was deleted, hiding a live worker. It now reads this checkout's lease refs from the remote (unlocked network read), then takes the workers lock, reloads each candidate's record (`_closed`: missing, `failed` or `terminated`), and deletes only those refs while still holding the lock. Every launch (`_launch_locked`) and resume (`_send`) pushes its lease under that same lock, so the two cannot interleave. If the remote is unreachable, the sweep does nothing; `sync` still reports, and the next sync retries.
- **P1 (2), a rejected push returned success:** under the coordinator's new offline rule, `acquire_lease` now refuses the turn when the push fails. After a failed push it runs one `ls-remote`. If that works, the remote is reachable and rejected the lease: `<remote> rejected the lease for W (…); nothing was launched`. Otherwise: `cannot reach <remote> to push the lease for W (…); retry, or pass --offline …`. `foreign_leases` likewise refuses when the remote cannot be read. On `delegate`, the refusal comes before any record exists when the first read fails. When the push fails, it comes after `create_record`, and that record goes `failed` with an `error` event, as in round 2. On `message`/`resume`, it comes before the `message` event and the spawn, and the record's state is unchanged.
- **`--offline`** on `delegate`, `message` and `resume` (`worker_cli.py`, passed as `offline=` to `ops.delegate`/`message`/`resume` and through to `foreign_leases`/`acquire_lease`): it reads and pushes no lease, counts this checkout's workers only, and prints one warning per remote per process. `offline` is added to `_with_op`'s default `--op-id` inputs and to `message`'s explicit inputs (only when set, so op ids recorded without the flag still match).
- **Removed:** the round-2 "warn and continue" path (`_OFFLINE`, `_offline`), which also stopped all lease reads for the rest of a process after one failure. A release that times out is still remembered (`_UNREACHABLE`), but only releases skip that remote, never a count or an acquire.
- **Docs:** the "What `max_workers` counts" paragraph now covers the locked sweep, the two refusals and `--offline`, including its op-id binding (398 lines).

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
- **sync** (`worker_reconcile.sync`): after its own lock section, `release_stale_leases` deletes this checkout's lease refs whose worker is no longer active here (locked in round 3).
- **No remote:** a repository without the remote configured pushes and reads nothing, which covers every existing test fixture. (Round 2's warn-and-continue for an unreachable remote is superseded by round 3.)
- **Removed:** `worker_ops.claimed_elsewhere` and its registry, owner and branch filters, and the test `test_a_claim_by_another_user_is_not_counted`, which asserted the rejected behaviour.
- **Docs** (`docs/orchestration-workers.md`): the "What `max_workers` counts" paragraph is rewritten for the lease. It covers the ref name, the checkout id, the recount after push, the lifetime, the sync sweep, offline behaviour and the network cost. The file stays at 398 lines.

## Weight of pushing on every launch

A launch costs one `ls-remote`, one push and one more `ls-remote`. A resume costs one push and one `ls-remote`, a close one push, and `sync` one `ls-remote`. Each call has a 20 s timeout. That seemed acceptable next to pickup's own push, so I didn't propose an alternative.

Two costs remain:
- `message`/`resume` run entirely under the workers lock, as before, so their push and `ls-remote` run under it too. The same is true of `delegate`'s acquire, the release in `wrapper_gone` (called from sweeps that hold the lock), and, from round 3, the stale sweep's delete. `delegate`'s first read and `terminate`'s release run outside it.
- A lease that could not be deleted (offline) over-counts in other checkouts until this checkout's next `sync`. That is the safe direction.

## Not new: `specy_road/worker_lease.py`

The touch zone named `worker_lease.py` as new, but that module already exists: it holds the human `handoff`/`reclaim` lease. The slot lease is a separate section in the same file (now 369 lines), and the module docstring says so. Round 3 needed `worker_cli.py`, which was added to the touch zones before I edited it. The registry schema and `validate` are unchanged.

## Acceptance

- **A1:** `delegate`, `message` and `resume` refuse a launch past `max_workers`. The count covers the main checkout and its linked worktrees (shared records) plus every other checkout's lease refs, whatever local branches exist and whoever owns the claim.
- **A2:** the docs paragraph above.
- **A3:** `tests/test_worker_max_workers_global.py` covers:
  - a resume refused at the limit: a lowered limit, a foreign lease on a branch that also exists locally, and leases from another owner;
  - two checkouts sharing one limit (`delegate` refused by the clone's lease);
  - the recount after push;
  - the lease's lifetime and the sync sweep;
  - the unreachable-remote refusal and `--offline`;
  - rejected lease pushes through `message`, `resume` and `delegate`;
  - the sweep keeping a lease created after its first read;
  - a missing checkout id created on use, an empty or unusable one refusing every turn, and concurrent first calls agreeing on one id;
  - an adopted worker in a second clone refusing a launch at `max_workers: 1`, an adopt whose lease cannot be pushed, `sync` pushing a missing lease, and a `delegate` retry answered while the remote is down.

## Verification (round 5)

As instructed, I ran only the touched test file, with the repository's `.conda` tools. The round-5 reviewer's rerun of `tests/test_worker_cli.py` passed (15), so the earlier report of `test_terminate_a_live_worker` failing did not reproduce there. I did not run that file myself.

- `/Users/savigil/WORKSPACE/specy-road/.conda/bin/pytest tests/test_worker_max_workers_global.py -q -p no:cacheprovider`: 24 passed in 37.14s.
- `/Users/savigil/WORKSPACE/specy-road/.conda/bin/specy-road file-limits`: OK.
- `/Users/savigil/WORKSPACE/specy-road/.conda/bin/ruff check` on `worker_lease.py`, `worker_ops.py`, `worker_reconcile.py` and the test file: all checks passed. Round 4's change, unlinted then, is covered by this run.

## Added

- `worker_lease.checkout_id`: the stable per-repository id, shared by linked worktrees (a uuid in the git common dir). Round 4: created by write-then-link, validated, and a `WorkerError` instead of `None`.
- `worker_lease._CHECKOUT_ID` (round 4): the 32-hex-digit shape an id must have to be used.
- `try/except WorkerError` around `checkout_id` in `release_lease` and `release_stale_leases` (round 4): releases stay best effort without an id.
- `worker_lease.LEASES`, `LEASE_TIMEOUT`: the ref namespace and a bound on every lease network call.
- `worker_lease._remote`: `(name, url)` of the integration remote, or `None` (no remote: no leases).
- `worker_lease.OFFLINE_HINT`, `_WARNED`, `_warn_offline` (round 3): the `--offline` hint in refusals, and one warning per remote per process when `--offline` is used.
- `worker_lease._UNREACHABLE` (round 3): a remote a release timed out on is not retried by later releases in the process; counts and acquires never consult it.
- `worker_lease._why` (round 3): the last line of git's error, for refusal messages.
- `worker_lease._lease_refs`, `foreign_leases(…, offline=)`: read lease refs, raising `WorkerError` when the remote is unreachable; count those of other checkouts; `offline` skips the read with a warning.
- `worker_lease.max_workers`: the policy limit, raising a `WorkerError` on an unreadable config rather than a `KeyError`.
- `worker_lease.slot_error`: the one refusal message, shared by the local and lease checks.
- `worker_lease.acquire_lease(…, new=, offline=)`: push, then recount, so simultaneous launches never exceed the limit. `new` decides whether a refusal withdraws the lease. Round 3: a failed push refuses (one `ls-remote` tells rejected from unreachable); an unreachable recount withdraws a new lease and refuses; `offline` skips it with a warning.
- `worker_lease.release_lease`: delete lease refs, best effort.
- `worker_lease.release_stale_leases` (renamed `sync_leases` in round 5, which also pushes a lease, under the lock and best effort, for each active record without one, and returns `(released, pushed)`): sync's sweep of this checkout's leases with no active local worker. Round 3: the recheck and delete run under the workers lock, through the new `_closed(repo_root, worker_id)` reload.
- `worker_ops.delegate/message/resume(…, offline=)`, `_launch_locked(…, offline)`, `_send(…, offline)` (round 3): carry `--offline` to the lease calls.
- `worker_cli._offline_arg` and `--offline` on `delegate`, `message` and `resume` (round 3), with `offline` bound into the `--op-id` inputs.
- `worker_ops._slot_or_existing(…, own=, foreign=)`: a resumed worker leaves itself out; `foreign` is the lease list read outside the lock.
- `worker_ops._launch_locked` lease guard: refused acquire → `error` event, `failed`, re-raise; release when the wrapper cannot start.
- `worker_ops._send`: `acquire_lease` before the message event and the spawn (A1 for resume).
- `worker_ops.terminate`: release after the lock.
- `worker_runner`: release on `_refuse`, on harness-start failure, and in `_exit_state` for `failed`.
- `worker_process.wrapper_gone`: release when a dead wrapper is marked `failed`.
- `worker_reconcile.sync`: `release_stale_leases` after the lock (`sync_leases` from round 5).
- `worker_lease._push_lease` (round 5): the lease commit and push, shared by `acquire_lease` and `sync_leases`.
- `worker_lease.acquire_lease(…, count=)` (round 5): `count=False` pushes without the recount, for `adopt`.
- `worker_lease.lease_adopted` (round 5): adopt's lease; one that cannot be pushed appends an `error` event, closes the record (`terminated`) and refuses the adopt.
- `worker_ops.adopt` (round 5): calls `lease_adopted` after `create_record`, under the lock.
- `worker_ops._slot_or_existing(…, foreign=None)` (round 5): without a foreign read, only the leaf's own worker is looked for and nothing is counted. `delegate`'s first lock section uses it, so a retry needs no network; `_send` passes `foreign=[]` for its local cap.
- File-limit housekeeping in `worker_ops.py` (round 1, no behaviour change): removed the unused `_now`, extra blank lines and a docstring line; `adopt`'s inner `fn` became an equivalent `mutate` lambda.
- Test `test_a_linked_worktree_shares_the_checkout_id_and_a_clone_does_not`: the checkout id's scope.
- Test `test_two_checkouts_share_one_limit`: A3, `delegate` refused by a clone's lease, no record left.
- Test `test_a_foreign_lease_counts_when_its_branch_also_exists_here`: review P1 (1), through public `resume`.
- Test `test_leases_from_another_owner_count`: review P1 (2), through public `message`, with no message event recorded.
- Test `test_a_lease_pushed_second_is_refused_and_withdrawn`: the recount after push, and the refused lease is deleted.
- Test `test_the_lease_follows_the_record`: an idle worker keeps its lease; `terminate` deletes it.
- Test `test_sync_releases_a_dead_or_stale_workers_lease`: the dead-wrapper release and the stale sweep.
- Test `test_an_unreachable_remote_refuses_unless_offline` (round 3, replacing the round-2 warn-and-continue test): `delegate` and `resume` refused with the `--offline` hint and no record; `delegate`, `resume` and `message` with `--offline` go ahead with exactly one warning.
- Test `test_offline_is_bound_into_the_op_id` (round 3): the same `--op-id` without `--offline` is refused as different arguments.
- Test `test_a_rejected_lease_push_refuses_message_and_resume` (round 3): a readable remote whose `update` hook rejects lease refs; `message` (CLI) and `resume` refused, the record stays idle, and no message event is recorded.
- Test `test_a_rejected_lease_push_refuses_a_launch` (round 3): `delegate` refused, its record `failed`, and no lease on the remote.
- Test `test_sync_keeps_a_lease_created_after_its_first_read` (round 3, review P1 (1)): a worker launched between the sweep's remote read and its delete keeps its lease, and the stale one is deleted. It wraps `worker_lease.run`, the public git runner the module imports, to land that launch.
- Tests kept from round 1: linked worktree counted, idle resume in its own slot, resume refused when local workers fill a lowered limit.
- Test helpers `_remote_and_clone`, `_leases`, `_idle`, `_foreign_worker`: a bare integration remote with a second clone, lease listing, an idle record, and a foreign worker holding its lease.
- Test `test_a_missing_checkout_id_is_created_and_the_count_still_holds` (round 4): `delegate` with no id file creates a valid id and is still refused by the other clone's lease.
- Test `test_an_empty_or_unusable_checkout_id_refuses_launch_and_resume` (round 4; parametrized over an empty file, a newline and a half-written id): `delegate` and `message` (CLI) and `resume` refused with "holds no checkout id"; no record is created, the idle worker keeps its state, and no message event is recorded. After the file is removed, a new valid id is written.
- Test `test_concurrent_first_calls_agree_on_one_checkout_id` (round 4): 32 calls on 8 threads return one id, matching the file, with no temporary file left.
- Test `test_an_adopted_worker_in_another_clone_counts` (round 5, R1): `ops.adopt` in the clone pushes a lease, and `delegate` of the same leaf in the first clone at `max_workers: 1` is refused with no record.
- Test `test_an_adopt_whose_lease_cannot_be_pushed_is_refused` (round 5): a rejecting remote refuses `ops.adopt`, and the record is `terminated`.
- Test `test_sync_pushes_a_lease_for_an_active_worker_without_one` (round 5): an active record with no lease gets one at `ops.sync`.
- Test `test_a_retry_returns_the_existing_worker_while_the_remote_is_down` (round 5, R2): with the remote unreachable, `delegate --json` returns the existing worker (`created: false`, exit 0). Once that worker is terminated, a real launch is refused with "cannot reach origin" and no new record.
- Test helper `_id_file` (round 4): the id file's path in the main checkout's git dir.
- Test helpers `_unreachable`, `_rejecting` (round 3): a remote path that does not exist (with `origin/HEAD` as last fetched), and a bare remote whose `update` hook rejects `refs/specy-road/*`.
- Mocks: one, round 3: `monkeypatch.setattr(lease, "run", …)` in the sweep-race test, which delegates every call to the real `run`. The remotes are real bare repositories in `tmp_path`.
