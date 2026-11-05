# Implementation summary — M15.25

## What changed

The post-run check reads each stash entry’s commit hash and subject (`git stash list --format=%H %gs`), parses the owning branch from the subject, and attributes add/remove deltas to the worker record on that branch. Observers get an informational `stash_other` note without `post_run_findings`; unattributable entries keep a `stash` finding on the observing worker with the subject quoted.

When either stash snapshot is `None` (git could not read the list), the turn gets exactly one `stash` finding whose summary includes `stash state unknown`, with no cross-worker attribution.

All per-hash decisions go through `_decide_stash_hash_change`, which consults `_attributed_hashes` before any self-branch violation or observer attribution so each hash produces at most one owner `post_run_check`.

When the stash **list** is unchanged across a turn but a push and pop both happened, we diff `git fsck --unreachable` snapshots (`GitState.stash_unreachable`) and attribute new stash-shaped commit subjects the same way as list deltas. Reflog was probed first; popped entries leave the reflog, so list+reflog at boundaries cannot see net-zero stashes.

## Touch zones (confirmed)

- `specy_road/worker_turn_check.py` — `GitState.stash` / `stash_unreachable`, `git_state`, delegate to `worker_turn_stash`, flag only non-`stash_other` findings, record `attributed_stash_hashes`
- `specy_road/worker_turn_stash.py` — attribution module
- `tests/test_worker_turn_stash.py` — parametrized and integration tests; `tests/test_worker_turn_check.py` — self-stash expectation

## Fix round (grok-4.7-low, pass 2)

**Class:** net-zero stash delta invisible to turn-boundary `git stash list` (push+pop inside another worker’s turn).

**Choice:** Reflog probe showed popped stash lines disappear from `refs/stash` reflog; unreachable stash commits remain until gc. Implemented unreachable-set diff when list snapshots match (variant of approach (a), not reflog). Ephemeral detection is skipped when either list snapshot is `None` or fsck fails.

## Probes

- `git reflog show refs/stash` after push+pop with empty stack — reflog ref deleted; popped entry not retained.
- `git reflog show refs/stash` after pop with another stash present — ephemeral line removed from reflog.
- `git fsck --unreachable` after push+pop — new `On …:` commit remains; diff attributes it during equal list snapshots.
- `test_ephemeral_stash_push_pop_during_observer_turn_flags_owner_not_observer` — B gets `stash_other`, A flagged once.
- Unknown list snapshot + unreachable diff — ephemeral path skipped when `before` or `after` stash is `None`.
- Second observer / owner pop dedup — still one owner event (`test_already_attributed_hash_skips_second_observer_and_owner_pop`).
- Reviewer pytest bundle (32 tests) — exit 0.
- `ruff check specy_road tests scripts` — exit 0.
- `specy-road file-limits` — OK.

## Added

- `stash_branch` — parse `On …:` / `WIP on …:` subjects; reject `(no branch)` in both forms
- `unreachable_commits` — parse `git fsck --unreachable` commit hashes
- `_commit_subject` — subject line for an ephemeral stash commit
- `_attributed_hashes`, `_owner`, `_rule_summary`, `_legacy_stash_summary`, `_attribute_owner`
- `_decide_stash_hash_change` — single gate for every changed hash
- `_list_delta_findings` / `_ephemeral_unreachable_findings` — list diff vs fsck diff when list unchanged
- `stash_findings` — unknown snapshot guard; orchestrates list and ephemeral paths
- `GitState.stash_unreachable` — snapshot for fsck diff at turn boundaries
- Tests — parametrized unknown/own/other/already-attributed; integration add/pop/ephemeral/self/unattributable
