# Implementation summary: M11.6 (`reconcile-current-contract`)

## Summary

`worker reconcile` (`specy_road/worker_reconcile.py`) now judges a worker
against the leaf's contract as it stands at reconcile time.

- **A1 (current zones):** reconcile already read the zones fresh on every run:
  `resolve_target` loads `roadmap/registry.yaml` from the coordinator's project
  root each time, and `ReviewTarget.touch_zones` prefers the claim row, which
  `edit-node` rewrites (`registry_claim_zones`, M10.14). Nothing in reconcile
  kept a delegation-time copy of the zones. I did not change the behaviour.
  I added a comment where the zones are read, and a test that widens the zones
  with `edit-node` after delegation and checks that the newly allowed path is
  no longer outside. That test also passes against the base commit, so it pins
  the behaviour rather than fixing it. If the field report's stale zones came
  from a run older than M10.14, this leaf has nothing more to change for A1.
- **A2 (merged-in paths):** `_integration_bases` takes the merge base of the
  worktree's `HEAD` with each integration ref: `refs/remotes/<remote>/<branch>`
  and `refs/heads/<branch>`, whichever exist. It reads both because a
  coordinator often merges a local integration branch that is ahead of its
  remote-tracking ref. `_changed_since` keeps a tracked path only if it also
  differs between the working tree and every such base. A file that a merge
  brought in matches the integration branch at that base, so it drops out of
  both `changed` and `outside_touch_zones`. Untracked files are always kept.
  When git cannot answer for a base, that base is skipped and the old result
  stands. Before any merge, the merge base is the fork point and the
  intersection changes nothing.
- **A3 (own contract only):** reconcile still compares hashes of the full
  prompt first. When the prompt differs, `_brief_unchanged` no longer compares
  whole briefs. It compares `own_contract(...)` of a fresh render and of the
  copy in the worktree. `own_contract` is section 1 of the brief (id, title,
  codename, type, execution hint, touch zones, goal, acceptance) without the
  two status lines, plus the leaf's own planning sheet block, which sits last in
  section 3. Everything else in the brief moves when the integration branch
  does and is ignored: the size line, ancestors, shared contracts,
  dependencies, the touch-zone instruction, rollup text and history. The goal
  counts as contract along with acceptance, touch zones and sheet, because it
  is in section 1 next to them. An unbuildable prompt still counts as a change.
  A missing worktree brief still falls back to the prompt-hash result.
- `docs/orchestration-workers.md`: the `reconcile W` row and the
  `needs_reconcile` flag description say this (lines replaced in place; the
  file is at 395 of 400 lines).

## Touch zones

Confirmed: `specy_road/worker_reconcile.py`, `docs/orchestration-workers.md`,
`tests/`. `specy_road/git_changed_paths.py` was not needed (`diff_paths`
already takes any comparison), so it is unchanged.

## Verification

- `pytest` (all `tests/test_*.py`, run in three foreground chunks because one
  run exceeds the 10-minute tool limit): 1058 passed; 909 passed, 2 skipped;
  997 passed.
- `pytest tests/test_worker_reconcile_contract.py`: 6 passed. Against the base
  `worker_reconcile.py`, the A2 test and the "integration branch moving" test
  fail, as they should. The A1 test and the three own-contract cases pass there
  too (see A1 above).
- `specy-road file-limits`: OK.
- `scripts/check_test_private_imports.py`: 0 new. It reports one stale entry,
  `review_packet._changed`, which was stale before this change.
- `ruff check` on the changed Python files: clean.

## Added

- `worker_reconcile._integration_bases`: merge bases of HEAD with the
  remote-tracking and local integration refs; these are the points the branch
  last took the integration branch in (A2).
- `bases` parameter and intersection loop in `worker_reconcile._changed_since`:
  drops tracked paths the tree matches the integration branch on (A2).
- Guard `own is not None` in that loop: a base git cannot diff is skipped, so
  it cannot empty the change list.
- `worker_reconcile.own_contract`: the leaf's own contract sections of a
  rendered brief (A3).
- `worker_reconcile._between` (anchored to a line start): extracts a section.
  It is anchored because the brief's size line also names `## 1. Execution
  target`.
- `worker_reconcile._STATUS_LINES`: the status lines left out of the contract.
  Pickup and progress change them; they are not contract.
- `tests/test_worker_reconcile_contract.py`: new.
  - `_linked`: a coordinator on `dev` with a checkpointed worker in a linked
    worktree, so coordinator edits do not show up as worker changes.
  - `_edit`: runs `edit-node` in-process, the same way
    `test_roadmap_crud_edit_claim_zones.py` does.
  - `test_reconcile_reads_the_zones_edit_node_widened_after_delegation` (A1).
  - `test_paths_merged_in_from_the_integration_branch_are_not_the_workers` (A2,
    including a remote-tracking ref behind the merged local branch).
  - `test_the_integration_branch_moving_is_not_a_contract_change` (A3: a shared
    README and a status change).
  - `test_a_change_to_the_leafs_own_contract_is_reported`, parametrized over
    acceptance, touch zones and sheet (A3).
- Mocks: none.
