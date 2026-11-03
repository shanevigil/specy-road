# Implementation summary: M11.52 — PR mode predicts and resolves the registry conflict

## What changed

Under `on_complete: pr`, `finish-this-task` now checks, after the bookkeeping
commit and before `--push`, whether the PR will merge:

1. It fetches the integration branch from the remote (a failed fetch keeps the
   last tip seen) and trial-merges that tip (`base_ref`: remote-tracking first)
   into the finish commit with `trial_merge` from `review_gate_ready`.
2. No conflict: nothing changes; the PR tail prints as before.
3. Conflicts only on `roadmap/registry.yaml`, `roadmap.md`, `roadmap-context.md`
   (`DETERMINISTIC_PATHS`): it runs `git merge --no-commit --no-ff <tip>` on the
   feature branch, writes the integration tip's registry minus this leaf's row
   (the tip's blob byte for byte when there is no row to drop), renders the two
   generated files again with merge mode's renderer, commits
   `Merge <ib> into <branch>`, and reconciles the digest against the new commit
   (`reconcile_or_rollback`, as merge mode does). Then `--push` pushes as before.
4. Any other conflict (code, or a bookkeeping path such as a chunk JSON): it names
   the paths, pushes nothing, leaves the bookkeeping commit as the tip with no
   merge in progress, prints the manual steps and exits 1. A merge that git
   itself refuses, or a resolution failure, is reported the same way, after
   `git merge --abort`.

A milestone rollup finish (which lands the leaf into the rollup branch, not via
a PR) skips the step. `auto` and `merge` are unchanged.

The registry is read from the integration side (`MERGE_HEAD`'s ref), not `HEAD`:
merge mode's `resolve_deterministic_paths` assumes `HEAD` is the integration
branch, which is the reverse of this merge's direction, so it could not be reused
as is; its `_regenerate_generated_files`, `reconcile_or_rollback`,
`unmerged_paths`, `merge_in_progress` and `DETERMINISTIC_PATHS` are.

## Files

- `specy_road/finish_pr_merge.py` (**new, outside the listed touch zones**): the
  fetch, trial merge, resolving merge and the exit. `finish_modes.py` is at 337
  lines against the 400 cap, and this is ~110 lines, so it went in a new module
  as the prompt directs. Please add it to the leaf's touch zones.
- `specy_road/bundled_scripts/finish_task.py`: `_bookkeeping_commit_phase` takes
  `pr_integration=(ib, remote)` and calls the new step between commit and push;
  `_resolve_main_context` keeps the rollup flag it already computed (`ctx["rollup"]`)
  so `main` passes `pr_integration` only under `pr` without a rollup.
- `docs/git-workflow.md`: the `pr` bullet describes the step; the "Bookkeeping is
  resolved, not merged" paragraph names the `pr` merge too.
- `tests/test_finish_pr_mode_merge.py` (new).

`specy_road/finish_modes.py` and `specy_road/review_gate_ready.py` are unchanged
(the latter is reused). Final touch-zone list: `specy_road/bundled_scripts/finish_task.py`,
`specy_road/finish_pr_merge.py`, `tests/`, `docs/git-workflow.md`.

## Verification

- `python -m pytest tests/test_finish_pr_mode_merge.py -q` — 4 passed (2 cases × embedded and nested `sr/` layouts).
- Red-green: with `finish_task.py` at the base commit, the same 4 tests fail.
- `specy-road file-limits` — OK.
- `python -m pytest -n auto -q` — 3299 passed, 2 skipped (docs edit landed mid-run; the 604 tests that read `docs/` re-run after it: passed).

## Notes

- After the resolving merge the feature branch tip is a merge commit, not the
  finish commit. Merge mode's re-run (`retry_merge_landing` →
  `refuse_unless_finish_tip`) would refuse that branch; that path only applies
  when a merge-mode landing failed, so the two do not meet in normal use.
- The fetch runs whether or not `--push` is given, so the check reflects the tip
  the PR will merge into.

## Added

- `specy_road/finish_pr_merge.py` — new module; holds the PR-mode step because `finish_modes.py` has no room under the 400-line cap.
- `pr_merge_integration_or_exit` — fetch, trial merge, resolve-or-refuse; the A1 entry point called before push.
- `merge_integration_resolving_bookkeeping` — the staged merge plus deterministic resolution, aborting on any stray conflict; A1's "commits a merge" branch.
- `_registry_from` — integration tip's registry minus this leaf's row (byte-for-byte checkout when no row to drop; HEAD's copy when the tip has none); merge mode's resolver reads the wrong side for this direction.
- `_abort` — `git merge --abort` and return the reason, so every failure leaves the branch at the finish commit.
- Guard: `stray` unmerged paths after the real merge, checked again even though the trial merge already passed, so a disagreement between `merge-tree` and `merge` cannot commit a code conflict.
- Guard: `not merge_in_progress` → nothing to commit (clean) or abort with git's message (refused merge).
- `_bookkeeping_commit_phase(pr_integration=...)` kwarg and `ctx["rollup"]` — wiring; rollup finishes do not open a PR, so they skip the step.
- `tests/test_finish_pr_mode_merge.py::lane` fixture — embedded and nested layouts with a bare `origin`; nested because conflicted paths are named from the git root.
- `_push_to_dev` helper — moves remote `dev` from a second clone, as another lane's pickup does, leaving this checkout's `origin/dev` stale so only the post-commit check can see it.
- `test_claim_gained_after_pickup_is_resolved_and_the_branch_merges_cleanly` — A2 first case: registry resolved, pushed tip merges `dev` cleanly and keeps the other claim, digest lists it.
- `test_code_conflict_is_named_and_nothing_is_pushed` — A2 second case: `src/a.py` named, remote branch unchanged, no merge left in progress.
- Mocks: none.
