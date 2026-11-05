# Implementation summary: M16.68 — finish resolves roadmap chunk conflicts the branch only inherited

Code commit: `2bbab82b` (base `e7058930`).

## What changed

- **A1.** When finish's landing merge conflicts in `roadmap/manifest.json` or a JSON chunk under
  `roadmap/` (alongside, or instead of, the registry and the two generated files), finish checks
  whether the branch edited those files itself. If it did not, each conflicted graph file takes the
  integration branch's version (`git checkout HEAD`, or `git rm` when integration removed it). Then
  the bookkeeping commit's one graph edit is applied again: the finished leaf set to Complete, plus
  any ancestors that rolled up with it, using the same `complete_rolled_up_ancestors` that finish's
  bookkeeping uses. The existing registry resolution and the `roadmap.md` / `roadmap-context.md`
  regeneration (export and digest, plus the post-commit digest reconcile) then run as before.
  `roadmap.md` was already a deterministic path.
- **"No edit of its own"** (`branch_roadmap_edits`): one `git log -c --name-only HEAD..MERGE_HEAD --
  <paths>`. A non-merge commit touching a path counts as the branch's own edit. The exception is
  finish's bookkeeping commit, matched by its subject `chore(rm-<codename>): complete, deregister`.
  A merge commit counts only where its result differs from every parent (a hand-made resolution),
  so content brought in by earlier merges of the integration branch does not count. If git cannot
  answer, every path counts as edited. The node to complete again is the codename's row in the
  registry at `<bookkeeping>^`. If integration no longer has the node in its graph (for example,
  archived), it is left as it is.
- **A2.** If the branch edited a conflicted graph file itself, the merge is aborted with one reason
  that names each file and the next command (``on <branch> run `git merge <integration>`, resolve
  those files, commit, then re-run finish``). That reason reaches finish's existing
  `merge_landing_failed` path, so M15.40's undo removes the bookkeeping commit. The branch's edit is
  never dropped.
- **Milestone rollup** (`milestone_rollup_git._cherry_pick_deterministically`): it uses the same
  classifier. The picked bookkeeping commit counts as bookkeeping, so it resolves the same way.
  The classifier now strips the project prefix, as the merge path already did. Before, the
  cherry-pick compared git-root paths against project-relative ones, so in the nested `sr/` layout
  it treated a registry conflict as a stray conflict.
- The merge commit message gets one extra paragraph naming the graph files resolved, and only when
  some were.

## Touch zones (final)

- `specy_road/finish_land_deterministic.py`
- `specy_road/milestone_rollup_git.py`
- **`specy_road/finish_land_roadmap_graph.py` (new module; please add it to the zones).** The
  project's `sr/constraints/file-limits.yaml` caps toolkit files at 400 lines, and keeping the new
  code in `finish_land_deterministic.py` took it to 519. The graph-specific code lives here:
  classification, edit detection, refusal text, resolution and the Complete re-application.
- `tests/test_finish_land_deterministic.py`

No change outside these files. The out-of-zone callers (`finish_land_integration`, `finish_land_local`,
`finish_modes`, `finish_pr_merge`, `reconcile_branch`, `do_next_task_register`) are unchanged.
`finish_pr_merge` keeps its own registry-only resolution (the PR path, not this leaf's merge landing).

## Quality checks

- C901 per function, compared with the base: `merge_feature_deterministically` 10 → 10,
  `resolve_deterministic_paths` 2 → 2, `_commit_message` 1 → 1, `_cherry_pick_deterministically`
  9 → 9. No new function is over 6.
- `ruff check` is clean, every new line is at most 100 characters, and `specy-road file-limits`
  passes.

## Verification

- `python -m pytest -q tests/test_finish_land_deterministic.py`: 12 passed.
- `python -m pytest -q -n 4`: 4989 passed.
- Red-green: with the base versions of the two source files restored, both new parametrized cases
  fail (inherited-only: the landing fails on the chunk conflict; own-edit: the error does not name
  the chunk).

Estimated net line change (informational, not a gate): about +250 package lines, +75 test lines.

## Added

- `finish_land_roadmap_graph.py` (new module): holds the graph-conflict logic so that
  `finish_land_deterministic.py` stays under the 400-line cap.
- `BOOKKEEPING_SUBJECT`: identifies finish's own bookkeeping commit, so its status flip is not
  counted as the branch's edit.
- `is_roadmap_graph_path`: states once which paths are roadmap graph files (`roadmap/**.json`).
- `split_conflicts`: separates graph conflicts from stray ones, project-prefix aware, shared by the
  merge and the cherry-pick.
- `branch_roadmap_edits`: decides A1 versus A2 (the branch's own edit, or inherited content).
- `own_roadmap_edit_refusal`: the one-line A2 reason, naming the files and the next command.
- `take_integration_graph`: resolves each graph file to integration's version. A path integration
  removed is removed here too (guard).
- `_finished_node_id`: finds the node the bookkeeping completed, from the registry before the
  bookkeeping commit.
- `_complete_again`: applies the bookkeeping's Complete status again on top of integration's
  version (guard: skips a node that is missing or already Complete).
- `resolve_graph` / `GraphResolveError`: the entry point and its failure type; the deterministic
  module maps the failure to `DeterministicResolveError` in `_resolve_graph`.
- `resolvable_conflict` (`finish_land_deterministic`): the shared classify-or-refuse step for the
  merge and the cherry-pick, which keeps both callers' C901 score unchanged.
- `_graph_note`: the extra commit-message paragraph, as a helper so that `_commit_message` keeps
  its complexity.
- `resolve_deterministic_paths(graph_paths=, bookkeeping=)`: new keyword arguments; their defaults
  keep the old behaviour.
- Test `test_a_roadmap_chunk_conflict_lands_only_when_the_branch_inherited_it`, parametrized
  `inherited-only` / `own-edit`: covers A3. It runs end-to-end `finish-this-task` in merge mode
  after integration moved the node (A1: lands with Complete, integration's move, the inherited goal,
  and `export --check` / `digest --check` clean; A2: exit 1, one error line naming the chunk and
  `git merge dev`, branch back at its pre-finish commit, origin unchanged).
- Test helper `_chunk_commit`: commits an edit to M1.1 in canonical chunk form for that test.
- Mocks: none.
