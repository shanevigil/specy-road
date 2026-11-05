# Implementation summary — M15.25

## What changed

The post-run check now reads each stash entry’s commit hash and subject (`git stash list --format=%H %gs`), parses the owning branch from the subject, and attributes add/remove deltas to the worker record on that branch. Observers get an informational `stash_other` note without `post_run_findings`; unattributable entries keep a `stash` finding on the observing worker with the subject quoted.

When either stash snapshot is `None` (git could not read the list), the turn gets exactly one `stash` finding whose summary includes `stash state unknown`, with no cross-worker attribution.

All per-hash decisions go through `_decide_stash_hash_change`, which consults `_attributed_hashes` before any self-branch violation or observer attribution so each hash produces at most one owner `post_run_check`.

## Touch zones (confirmed)

- `specy_road/worker_turn_check.py` — `GitState.stash` shape, `git_state` stash capture, delegate stash comparison to `worker_turn_stash`, flag only non-`stash_other` findings, record `attributed_stash_hashes` on the turn event
- `specy_road/worker_turn_stash.py` — attribution module
- `tests/test_worker_turn_stash.py` — parametrized and integration tests; `tests/test_worker_turn_check.py` — expect `stash_rule_violation` for self-stash

## Fix round (grok-4.7-low)

- **Unknown snapshot class** — `None` before/after no longer coerced to `()`; one unknown finding on the observing worker only.
- **Duplicate attribution class** — self-branch and observer paths both route through `_decide_stash_hash_change`, which skips hashes already in the owner’s `attributed_stash_hashes`.
- **WIP detached subject** — `WIP on (no branch): …` treated like `On (no branch): …` (no branch parse).

## Probes

- `stash_findings` with `before=None` and a foreign `On feature/rm-thing:` entry — one `stash` unknown finding, zero owner events.
- `stash_findings` with `after=None` and a prior entry — same unknown behaviour, no owner events.
- Second observer `stash_findings` after B attributed a hash — `[]`, owner still one `post_run_check`.
- Owner removal diff after observer attribution — `stash_findings` returns `[]`, owner event count stays 1.
- `stash_branch('WIP on (no branch): …')` — `None`, falls through to legacy `stash` finding when no worker matches.
- `close_turn` after B pop mid-turn — owner exactly one attributed event (integration test).
- Reviewer command bundle (`test_worker_turn_stash`, `test_worker_turn_check`, `test_headless_limits_denials`, `-n 4`) — exit 0.

## Added

- `stash_branch` — parse `On …:` / `WIP on …:` subjects; reject `(no branch)` in both forms
- `_attributed_hashes` — read prior `attributed_stash_hashes` from owner events
- `_owner` — map branch to a worker record via `list_records`
- `_rule_summary` / `_legacy_stash_summary` / `_UNKNOWN_STASH_SUMMARY` — finding text
- `_attribute_owner` — append owner `post_run_check` when an observer attributes
- `_decide_stash_hash_change` — single gate for every changed hash (self, other, legacy, dedup)
- `stash_findings` — unknown-snapshot guard; iterate diffs through `_decide_stash_hash_change`
- Parametrized tests — unknown before/after, own branch, other branch
- `test_already_attributed_hash_skips_second_observer_and_owner_pop` — dedup probes
- Integration tests — cross-worker add/pop, self-stash, unattributable `stash store`
