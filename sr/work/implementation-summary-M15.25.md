# Implementation summary — M15.25

## What changed

The post-run check reads each stash entry’s hash and subject (`git stash list --format=%H %gs`), parses the owning branch, and attributes list deltas to the worker on that branch.

`post_run_check_flags_worker` in `worker_turn_stash.py` decides whether a turn sets `post_run_findings`: `stash_other` notes alone leave the observer unflagged; violations, legacy `stash` findings, and stream findings still flag.

Unknown stash snapshots produce one `stash` finding on the observing worker with no cross-worker attribution. Each hash is attributed at most once via `_decide_stash_hash_change`.

**A3 documented limit:** a stash pushed and popped entirely inside another worker’s turn is not visible to turn-boundary snapshots and is not detected (`test_ephemeral_stash_push_pop_during_observer_turn_is_not_detected`).

## Touch zones (confirmed)

- `specy_road/worker_turn_check.py` — `GitState.stash`, `%H %gs` in `git_state`, `stash_findings` in `git_findings`; `close_turn` calls `post_run_check_flags_worker` (A2 unflagged observer; one-line delegate)
- `specy_road/worker_turn_stash.py` — attribution and flag/note decision
- `tests/test_worker_turn_stash.py`

## Fix round (grok-4.7-low, pass 4)

**Class:** observer `stash_other` incorrectly flagged because WIP `close_turn` used `if found:`.

**Design:** single `post_run_check_flags_worker(findings)` for flag vs note; `close_turn` delegates to it. Ephemeral push+pop remains out of scope per planner A3 rewrite on WIP.

## Probes

- `post_run_check_flags_worker` parametrized — note-only false, violation/unknown true, note+denial true.
- `test_another_workers_stash_add_flags_owner_and_notes_observer` — B unflagged, `stash_other` in event, A flagged.
- `test_another_workers_stash_pop_during_observer_turn_flags_owner_not_observer` — A flagged, B unflagged.
- `test_ephemeral_stash_push_pop_during_observer_turn_is_not_detected` — matches A3 limit wording.
- `test_unknown_stash_snapshot_*` — flags observer, no owner events.
- Reviewer pytest bundle (37 tests) — exit 0.
- `ruff check specy_road tests scripts` — exit 0.
- `specy-road file-limits` — OK.

## Added

- `post_run_check_flags_worker` — flag vs note decision for a turn’s findings list
- `_NOTE_KIND`, consolidated `_decide_stash_hash_change` / `stash_findings`
- Parametrized `test_post_run_check_flags_worker` and observer/owner/unknown coverage in integration tests
