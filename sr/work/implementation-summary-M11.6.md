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
- **A2 (merged-in paths):** `_changed_since` keeps a tracked path changed
  since `since` (the checkpoint, or the HEAD the worker started at) only when
  one of two sources changed it. The first is the branch's own commits in
  `since..HEAD`, from `git_changed_paths.branch_commit_paths`: `git log
  --first-parent --cc --name-status -z` with rename and copy detection, both
  sides of a rename. The second is the uncommitted tree (`diff_paths(wt,
  "HEAD")`). `--first-parent` never walks the integration commits a merge
  brought in. `--cc` lists a merge's path only where the merge result differs
  from every parent, which is a conflict resolution or an edit folded into the
  merge. So a file that arrived only through a merge drops out of both
  `changed` and `outside_touch_zones`, whichever integration ref it came from:
  local, remote-tracking, stale or diverged. A later edit or deletion of that
  file by the worker is a commit on the branch's own line and is reported.
  Untracked files are always kept. When git cannot answer either query, the old
  unfiltered result stands. This replaces the merge-base rule of rounds 0 and 1
  (see review round 3).
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
`specy_road/git_changed_paths.py` (`branch_commit_paths`, from review round
3), `tests/`.

## Review round 1 (gpt-6.1-sol: block)

- R1: fixed as described under A2 (newest base only). The merge test now goes on
  past a checkpoint taken after the merge: with the stale remote-tracking ref in
  place, the worker deletes the merged file, and reconcile reports it in
  `changed` and `outside_touch_zones` and sets `needs_reconcile`. That
  continuation fails against the round-0 code (`[] == ['other/merged.txt']`).
- R2: the tests use the public `worker_repo` helper from
  `tests/test_worker_m310_reconcile_status.py` (the same repo `_repo` built)
  instead of the private `tests.test_worker_cli._repo`. Assertions are unchanged.
- Re-run in round 1: only `tests/test_worker_reconcile_contract.py` (6 passed),
  `scripts/check_test_private_imports.py` (0 new), `ruff check` on the two
  changed Python files (clean) and `specy-road file-limits` (OK). The full-suite
  numbers below are from round 0.

## Review round 3 (gpt-6.1-sol: block)

- A2: when the local and remote integration refs had diverged and both were
  merged, the newest-merge-base rule had no newest base. Filtering turned off
  and merge-only paths were reported. I replaced the merge-base rule with the
  commit-based rule under A2, which the reviewer suggested, restricted to the
  first-parent line. A plain `git log --no-merges <base>..HEAD` would also list
  the integration's own commits that a merge brought in, because they are
  reachable from HEAD.
- The merge regression is parametrized over `stale` (the round-1 case,
  unchanged) and `diverged`. In `diverged`, a remote-only commit is merged as
  well, and the merged-in files must not be reported. Both cases continue to
  the post-merge checkpoint and the worker deleting the merged file. Against
  the round-2 code, `diverged` fails: `other/merged.txt` and `other/remote.txt`
  are reported. `stale` passes on both.
- New: `test_an_edit_folded_into_a_merge_commit_is_the_workers` pins that an
  outside-zone file added inside a merge commit is still reported. It passes
  against the round-2 code too, so it guards the new rule against hiding such
  edits.
- `docs/orchestration-workers.md`: the `reconcile W` row states the new rule.
- Re-run in round 3: `tests/test_worker_reconcile_contract.py` (8 passed), the
  tests that use `git_changed_paths` (`tests/test_review_round6_evidence.py`,
  14 passed), `scripts/check_test_private_imports.py` (0 new), `ruff check`
  (clean) and `specy-road file-limits` (OK).

## Verification

- `pytest` (all `tests/test_*.py`, run in three foreground chunks because one
  run exceeds the 10-minute tool limit): 1058 passed; 909 passed, 2 skipped;
  997 passed.
- `pytest tests/test_worker_reconcile_contract.py` (round 0): 6 passed. Against the base
  `worker_reconcile.py`, the A2 test and the "integration branch moving" test
  fail, as they should. The A1 test and the three own-contract cases pass there
  too (see A1 above).
- `specy-road file-limits`: OK.
- `scripts/check_test_private_imports.py`: 0 new. It reports one stale entry,
  `review_packet._changed`, which was stale before this change.
- `ruff check` on the changed Python files: clean.

## Added

- `git_changed_paths.branch_commit_paths`: paths the branch's own
  first-parent commits changed, with a merge counted only where it differs from
  every parent; this is where the worker's own committed changes come from
  (A2, round 3).
- Intersection in `worker_reconcile._changed_since`: keeps a changed path only
  when the branch's own commits or the uncommitted tree changed it (A2).
- Guard that both git queries answered (`is not None`): otherwise the
  unfiltered result stands, so a git failure cannot empty the change list.
- `worker_reconcile.own_contract`: the leaf's own contract sections of a
  rendered brief (A3).
- `worker_reconcile._between` (anchored to a line start): extracts a section.
  It is anchored because the brief's size line also names `## 1. Execution
  target`.
- `worker_reconcile._STATUS_LINES`: the status lines left out of the contract.
  Pickup and progress change them; they are not contract.
- `tests/test_worker_reconcile_contract.py`: new.
  - `_linked`: a coordinator on `dev` (repo from the public `worker_repo`
    helper) with a checkpointed worker in a linked worktree, so coordinator
    edits do not show up as worker changes.
  - `_edit`: runs `edit-node` in-process, the same way
    `test_roadmap_crud_edit_claim_zones.py` does.
  - `test_reconcile_reads_the_zones_edit_node_widened_after_delegation` (A1).
  - `test_paths_merged_in_from_the_integration_branch_are_not_the_workers`,
    parametrized `stale` / `diverged` (A2). It covers a remote-tracking ref
    behind the merged local branch, or a diverged remote that was merged too.
    Past a checkpoint after the merge, the worker deleting the merged file is
    still reported (R1).
  - `test_an_edit_folded_into_a_merge_commit_is_the_workers` (A2: the merge
    commit's own edits are not dropped as merged-in).
  - `test_the_integration_branch_moving_is_not_a_contract_change` (A3: a shared
    README and a status change).
  - `test_a_change_to_the_leafs_own_contract_is_reported`, parametrized over
    acceptance, touch zones and sheet (A3).
- Mocks: none.
