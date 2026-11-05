# Implementation summary — M15.25

## What changed

The post-run check reads each stash entry’s hash and subject (`git stash list --format=%H %gs`), parses the owning branch, and attributes list deltas to the worker on that branch.

`post_run_check_flags_worker` decides whether a turn sets `post_run_findings` (`stash_other` notes alone do not flag the observer).

Per-hash attribution runs under `workers_lock`: read `_attributed_hashes` (events plus `work/.workers/stash-attributed-hashes` reservations), decide, then append the owner event or reserve for the owning worker’s deferred `close_turn` event. Concurrent observers therefore produce at most one owner `post_run_check` per hash.

**A3 documented limit:** push+pop entirely inside another worker’s turn is not detected (`test_ephemeral_stash_push_pop_during_observer_turn_is_not_detected`).

## Touch zones (confirmed)

- `specy_road/worker_turn_check.py` — `GitState.stash`, `git_state`, `stash_findings`, `post_run_check_flags_worker` in `close_turn`
- `specy_road/worker_turn_stash.py` — attribution, lock, reservation log
- `tests/test_worker_turn_stash.py`

## Fix round (gpt-6.1-sol-low)

**Class:** concurrent turn closure — check-then-append race on the same stash hash.

**Design:** one `workers_lock` critical section in `_decide_stash_hash_change`; `_reserve_stash_hash` records own-worker attribution before `close_turn` writes the single turn event.

## Probes

- `test_concurrent_observers_attribute_one_stash_hash_at_most_once` — two threads, barrier, one owner event.
- Sequential dedup test — still one owner event after pop/second observer.
- `post_run_check_flags_worker` parametrized cases — unchanged.
- Reviewer pytest bundle (38 tests) — exit 0.
- `ruff check specy_road tests scripts` — exit 0.
- `specy-road file-limits` — OK.

## Added

- `_attribution_log`, `_reserve_stash_hash` — persist reservations under `workers_lock`
- `workers_lock` around read/decide/append in `_decide_stash_hash_change`
- `test_concurrent_observers_attribute_one_stash_hash_at_most_once` — public `stash_findings` race regression
