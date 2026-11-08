# M16.1.9 — Public milestone scenarios

Nine scenarios under `tests/scenarios/milestone/` drive the milestone session, chunk IO, rollup git, reconcile and PR hint through CLI `main()` or other public functions. No package file changed. No scenario failed, so none is an `xfail`.

Touch zone confirmed: `tests/scenarios/milestone/`. Pytest collects that directory without a parent `__init__.py`, so nothing outside the zone was added.

The full suite at this base, excluding the new directory, was 6887 passed and 14 skipped (`pytest -n 4`). The nine new tests pass on their own.

Net test change: **+331 lines** in three new files (the estimate was about +300). Not a gate.

## Coverage of the listed modules

Line and branch coverage, measured with coverage 7.17.2 and branch arcs on. **Before** is the suite above. **After** is that data unioned with the nine scenario tests. Reported only; not a pass/fail gate.

| Module | Lines before | Lines after | Branches before | Branches after |
| --- | --- | --- | --- | --- |
| `specy_road/milestone_chunk_io.py` | 41/70 (58.6%) | 57/70 (81.4%) | 12/30 (40.0%) | 17/30 (56.7%) |
| `specy_road/milestone_rollup_git.py` | 71/96 (74.0%) | 74/96 (77.1%) | 23/36 (63.9%) | 23/36 (63.9%) |
| `specy_road/bundled_scripts/start_milestone_session.py` | 49/89 (55.1%) | 70/89 (78.7%) | 7/16 (43.8%) | 10/16 (62.5%) |
| `specy_road/bundled_scripts/reconcile_milestone_status.py` | 74/103 (71.8%) | 88/103 (85.4%) | 22/48 (45.8%) | 32/48 (66.7%) |
| `specy_road/bundled_scripts/open_milestone_pr.py` | 15/36 (41.7%) | 32/36 (88.9%) | 1/8 (12.5%) | 5/8 (62.5%) |

`milestone_rollup_git` was already the best covered of the five. The cherry-pick and merge scenarios take the happy path the suite already reaches in part, so their branch total does not move. The session, chunk, reconcile and PR scenarios are what the research table had left thin, and those four rise.

## Scenarios

- `start-milestone-session` on parent `M2` creates `feature/rm-milestone-two` from `dev`, writes `work/.milestone-session.yaml`, and stores an active `milestone_execution`.
- `write_milestone_execution` persists that lock. Promotion stays `active` while a leaf is open, and sets `pending_mr` once every structural leaf is Complete.
- `cherry_pick_bookkeeping_to_integration` lands the leaf's registry bookkeeping on `dev` and pushes it. `merge_leaf_into_rollup` merges the leaf into the rollup (a real merge, with the rollup's own commit as the first parent) and checks `dev` back out.
- `reconcile-milestone-status --apply` on an open plan (`state: active`, leaves Complete, rollup not merged) promotes to `pending_mr` and does not close the parent. On a closed plan it sets the parent status to Complete and leaves the execution closed. The full-review hold is off in that fixture so the computed rollup follows the leaves; with the hold on, both plans would print nothing.
- `open-milestone-pr` prints the `gh pr create` line from `feature/rm-milestone-two` to `dev`, with the parent title.

## Added

### Helpers

- `set_parent_codename` — `start-milestone-session` requires a codename, and validate requires the planning filename to match it.
- `push_origin` — session sync and the rollup git steps fetch a real remote.
- `milestone_repo` — the M2 graph on `dev`, published to `origin`, for the session scenario.
- `active_execution` — the lock document shared by the write, promotion and reconcile scenarios.
- `parent_node` — read the saved chunk back without a private loader.
- `landed_milestone` — both leaves Complete, with `milestone_full_review` off so the rollup follows the leaves and reconcile has a plan to print.
- `bookkeeping_repo` — one registry claim and `origin`, for the cherry-pick and the merge.

### Branches or guards

none

### Mocks

none

### Tests

- `test_start_milestone_session_creates_the_rollup_branch` — the session command creates the rollup branch and the active lock.
- `test_write_milestone_execution_stores_the_active_lock` — `write_milestone_execution` persists a valid active lock.
- `test_promotion_stays_put_while_a_leaf_is_open` — promotion does not move an open milestone.
- `test_promotion_sets_pending_mr_when_every_leaf_is_complete` — promotion sets `pending_mr` when every leaf is Complete.
- `test_cherry_pick_lands_bookkeeping_on_integration` — bookkeeping cherry-pick lands on integration and is pushed.
- `test_merge_leaf_into_rollup_keeps_the_leaf_and_returns_to_integration` — the rollup merge keeps the leaf and returns to integration.
- `test_reconcile_open_plan_promotes_when_leaves_are_complete` — an open plan promotes and does not close.
- `test_reconcile_closed_plan_completes_the_parent` — a closed plan completes the parent.
- `test_open_milestone_pr_prints_the_rollup_command` — `open-milestone-pr` prints the rollup PR command.
