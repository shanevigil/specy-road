# Implementation summary: M15.4 — parallel PR-mode leaves reconcile bookkeeping by rule

Branch `feature/rm-parallel-pr-leaves-reconcile-bookkeeping-by-rule`, base `a776508c`
(the two earlier `wip(M15.4)` commits carry the bulk; this round adds `8574f287`
on top, which fixes the regressions that work caused).

## What changed

- **A1, `reconcile-branch`.** New `specy_road/reconcile_branch.py` and the CLI
  `specy_road/bundled_scripts/reconcile_branch_cli.py`, wired up as one entry in
  `cli.py`'s script map, plus a usage line in `cli_usage.py`. Run in a leaf's
  worktree on `feature/rm-<codename>`, it refuses on a dirty tracked tree or the
  wrong branch. Otherwise it fetches the integration branch and calls
  `finish_pr_merge.merge_integration_resolving_bookkeeping`, which resolves the
  registry by rule and regenerates `roadmap.md` and `roadmap-context.md`. It then
  pushes the merge commit when the branch has an upstream. A conflict on any other
  path aborts the merge, names the paths and exits 1 with HEAD unchanged.
  `merge_integration_resolving_bookkeeping` gained `drop_row` (default `True`, so
  finish behaves as before). A branch that has not finished still holds its claim,
  so for it reconcile passes `drop_row=False` and the row stays.
- **A2.** `tests/test_reconcile_branch.py` builds two `on_complete: pr` leaves,
  merges the first into `dev`, then reconciles the second. It asserts there are no
  conflict markers, that `validate`, `export --check` and `digest --check` pass,
  that the code files are untouched, that the branch was pushed and that a forge
  merge would be clean. A code-conflict case asserts the refusal, an unchanged HEAD
  and no `MERGE_HEAD`.
- **A3, pickup.** The register step moved from `do_next_task.py` (now 366 lines)
  to `do_next_task_register.py`. After the row is written, it renders the
  *tracked* generated files again and commits the ones that changed with the
  registry, by explicit path (`register_and_commit` gained a `generated` callback).
  Abort's own-registration check moved to `abort_task_pickup_own_commit.py`. It now
  accepts a commit whose paths are the registry plus at most the two generated
  files, and the registry still has to differ only by this claim's row.
  `tests/test_pickup_register_digest.py` covers `digest --check` / `export --check`
  right after pickup, on both branches, and abort after the new register commit.
- **A4.** New `docs/git-workflow-parallel-prs.md` says when to run the command and
  why it is a command and not a `.gitattributes` driver (forge merges do not run
  custom drivers). `docs/git-workflow.md` links it in one line (now 384 lines). The
  finish stub `specyrd-finish.md` has a paragraph with the same points.

## This round (rework after `w-0025` hit its usage limit)

The earlier WIP commits passed their own tests, but they broke 12 existing tests:

1. `do_next_task_register` imported its own `git_run`, so tests that patch
   `do_next_task.git_run` ran real git. `register_claim` now takes `git_runner`,
   and `do_next_task` passes `lambda *a: git_run(ROOT, *a)`, which puts the
   patch point back where it was.
2. The register step rendered `roadmap.md` / `roadmap-context.md` even in projects
   where git does not track them. That left new untracked files, and the next
   clean-tree check refused (`tests/test_pickup_second_claim_guard.py`). It now
   renders only the generated files that `git ls-files --error-unmatch` reports as
   tracked.
3. `abort_task_pickup_own_commit.only_own_registration_ahead` called its own
   `git_capture`, which bypassed the `abort_task_pickup.git_capture` patch in
   `tests/test_abort_task_pickup.py`. It now takes `capture=` and abort passes
   its own function.

Verification: `pytest -q -n 4` (whole suite) gives 4029 passed. `specy-road
file-limits` is OK. `specy-road validate --repo-root tests/fixtures/specy_road_dogfood`
is OK.

## Touch zones (final)

These are the same as the brief's list. Nothing outside them was changed. The
call sites outside the zones (`grind_session_in_flight.py`,
`validate_stale_commands.py`, `finish_task.py`) did not need changes:
`drop_row` defaults to finish's behaviour, and the helper signatures they use
did not change.

## Added

### Helpers / modules
- `specy_road/reconcile_branch.py` `reconcile_branch`: the A1 command body (guard, fetch, merge by rule, push).
- `reconcile_branch._holds_claim`: decides `drop_row`, so an unfinished branch keeps its claim row.
- `reconcile_branch._push`: pushes to the configured upstream, or prints a hint when there is none.
- `specy_road/bundled_scripts/reconcile_branch_cli.py` (`main`, `_parse_args`, `_codename`): the CLI with `[NODE_ID] --base --remote --repo-root`.
- `do_next_task_register.register_claim`: the register step moved out of `do_next_task.py` for the 400-line cap (A3).
- `do_next_task_register.regenerated_tracked_paths`: renders the tracked generated files and returns those that changed.
- `abort_task_pickup_own_commit.registers_only` / `only_own_registration_ahead`: moved from `abort_task_pickup.py`; now also accept the two generated paths.

### Branches / guards / parameters
- `merge_integration_resolving_bookkeeping(drop_row=True)`: lets reconcile keep the claim row of an unfinished leaf.
- `register_and_commit(generated=None)`: commits the regenerated paths with the registry by explicit path.
- `register_claim(git_runner=...)`: keeps the `do_next_task.git_run` patch point (this round).
- Tracked-only rendering in `regenerated_tracked_paths`: stops pickup from leaving untracked generated files (this round).
- `only_own_registration_ahead(capture=...)`: keeps the `abort_task_pickup.git_capture` patch point (this round).
- reconcile refusals: not on a `feature/rm-*` branch, `NODE_ID` names a different leaf, dirty tracked tree, missing base ref.

### Mocks
- none (the new tests use real git repos and a bare remote).

### Tests
- `test_reconcile_resolves_bookkeeping_and_pushes`: A2 two-leaf scenario.
- `test_reconcile_refuses_a_code_conflict_and_leaves_the_branch`: A2 refusal with HEAD unchanged.
- `test_reconcile_keeps_the_row_of_a_leaf_that_has_not_finished`: the `drop_row=False` path, and the no-upstream message.
- `test_reconcile_refuses_off_a_leaf_branch_and_on_the_wrong_leaf`: branch guards, plus the CLI entry with `NODE_ID`.
- `test_pickup_commits_the_digest_with_the_claim`: A3 `digest --check` on both branches right after pickup.
- `test_abort_drops_a_local_register_commit_that_carries_the_digest`: A3 abort accepts the new commit and refuses an amended one.
