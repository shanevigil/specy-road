# Implementation summary — M15.25

## What changed

The post-run check reads each stash entry’s commit hash and subject (`git stash list --format=%H %gs`), parses the owning branch from the subject, and attributes list deltas to the worker on that branch. Observers get a `stash_other` note; unattributable entries keep a `stash` finding on the observing worker with the subject quoted.

When either stash snapshot is `None`, the turn gets exactly one `stash` unknown finding and does not attribute to other workers.

Each stash hash is attributed at most once via `_decide_stash_hash_change` and `_attributed_hashes` (from owner `post_run_check` findings and `attributed_stash_hashes`).

**Documented limit:** a stash pushed and popped entirely inside another worker’s turn is not detected — turn boundaries only compare `git stash list`, which is unchanged. Reflog does not retain popped entries; planner chose not to extend `worker_turn_check.py` with fsck/unreachable snapshots (option b).

## Touch zones (confirmed)

- `specy_road/worker_turn_check.py` — `GitState.stash` only, `%H %gs` in `git_state`, single `stash_findings` call (A1); `close_turn` matches WIP
- `specy_road/worker_turn_stash.py` — list-based attribution
- `tests/test_worker_turn_stash.py` — parametrized + integration tests including ephemeral limit pin

## Fix round (grok-4.7-low, pass 3 — planner scope)

**Class:** A1 boundary — fsck/`stash_unreachable` and extra `close_turn` detail in `worker_turn_check.py`.

**Change:** Removed unreachable detection; `git diff origin/WIP/improvements-0-3-1 -- specy_road/worker_turn_check.py` is import + `GitState.stash` + `git_state` parse + one `stash_findings` line only. Dropped `if h:` guard on stash lines.

**A2 note:** With WIP `close_turn` (`if found:`), a turn whose only findings are `stash_other` still sets `post_run_findings` on the observer. Unflagged `stash_other` needs an A1 amendment to `close_turn` or a human-approved hook outside this file.

## Probes

- `git diff origin/WIP/improvements-0-3-1 -- specy_road/worker_turn_check.py` — no `stash_unreachable`, no fsck, no `close_turn` edits.
- `test_ephemeral_stash_push_pop_during_observer_turn_is_not_detected` — clean B turn, no owner events.
- Unknown snapshot parametrized tests — one `stash` finding, no owner attribution.
- `test_already_attributed_hash_skips_second_observer_and_owner_pop` — one owner `post_run_check`.
- Reviewer pytest bundle (32 tests) — exit 0.
- `ruff check specy_road tests scripts` — exit 0.
- `specy-road file-limits` — OK.

## Added

- `stash_branch`, `_attributed_hashes`, `_owner`, `_decide_stash_hash_change`, `stash_findings` — list-only attribution
- Parametrized and integration tests as above
- `test_ephemeral_stash_push_pop_during_observer_turn_is_not_detected` — documents net-zero list delta limit
