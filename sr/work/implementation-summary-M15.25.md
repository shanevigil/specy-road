# Implementation summary — M15.25

## What changed

The post-run check now reads each stash entry’s commit hash and subject (`git stash list --format=%H %gs`), parses the owning branch from the subject, and attributes add/remove deltas to the worker record on that branch. Observers get an informational `stash_other` note without `post_run_findings`; unattributable entries keep a `stash` finding on the observing worker with the subject quoted.

## Touch zones (confirmed)

- `specy_road/worker_turn_check.py` — `GitState.stash` shape, `git_state` stash capture, delegate stash comparison to `worker_turn_stash`, flag only non-`stash_other` findings, record `attributed_stash_hashes` on the turn event
- `specy_road/worker_turn_stash.py` — new module
- `tests/test_worker_turn_stash.py` — new acceptance tests; `tests/test_worker_turn_check.py` — expect `stash_rule_violation` for self-stash

## Added

- `stash_branch` — parse `On …:` / `WIP on …:` subjects for the branch name
- `_attributed_hashes` — skip duplicate owner events for the same stash hash
- `_owner` — map branch to a worker record via `list_records`
- `_rule_summary` / `_legacy_stash_summary` — finding text for violations vs unattributable stash deltas
- `_attribute_owner` — append `post_run_check` + flag on another worker’s record when their branch stashed
- `stash_findings` — core attribution and observer notes
- `test_stash_branch_reads_on_and_wip_subjects` — subject parsing
- `test_another_workers_stash_pop_during_observer_turn_flags_owner_not_observer` — A3 pop case via linked worktree
- `test_another_workers_stash_add_flags_owner_and_notes_observer` — A3 add case; B unflagged with `stash_other`
- `test_own_turn_stash_is_a_rule_violation_on_this_worker` — A3 self-stash
- `test_stash_with_no_matching_worker_keeps_stash_finding_on_observer` — A3 unattributable `stash store` subject
