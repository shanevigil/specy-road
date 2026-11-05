# Implementation summary: M16.68 — finish resolves roadmap chunk conflicts the branch only inherited

Commits: `2bbab82b` (first pass), `3c054c88` (merge of WIP for the revised acceptance), `abf29634`
(plan-review changes). Base `e7058930`.

## What changed

- **A1.** Finish's landing merge can conflict in `roadmap/manifest.json` or a JSON chunk under
  `roadmap/`, alone or with the registry and the two generated files. When it does, finish checks
  who wrote each conflicted graph file's changes on the branch (provenance, below).
  - **Nothing authored in the conflicted files:** each file takes the integration branch's version
    (`git checkout HEAD`, or `git rm` when integration removed it).
  - **Completion applied again:** finish sets the finishing node back to Complete, finding it by
    `node_key`. The key comes from the graph file the bookkeeping commit wrote, and the node id from
    the codename's registry row at `<bookkeeping>^`. Ancestors are then recomputed with
    `complete_rolled_up_ancestors`. A node the integration branch no longer has, for example because
    it was archived, is left alone.
  - **Then, as before:** the registry is resolved (claim released), `roadmap.md` and
    `roadmap-context.md` are regenerated, and the digest is reconciled after the commit.
- **Provenance** (`branch_roadmap_edits`, as in the adopted plan review): the check walks
  `git log --first-parent HEAD..MERGE_HEAD`.
  - **This run's bookkeeping commit:** if the tip has the subject
    `chore(rm-<codename>): complete, deregister`, it is set aside before classifying. Its status
    edits are finish's, not the branch's.
  - **Ordinary commits:** every graph path a commit changes counts as authored.
  - **Merges:** a merge authors a path it changes against its first parent, except where its blob
    (or deletion) matches an integration parent's. An integration parent is any non-first parent
    the integration HEAD contains.
  - **When git can't list the history:** every path counts as authored.
  - **What triggers a refusal:** only authored edits in conflicted paths. An authored graph edit
    that doesn't conflict merges normally.
- **A2.** An authored edit in a conflicted graph file aborts the merge. The single reason line names
  each file and the next command: ``on <branch> run `git merge <integration>`, resolve those files,
  commit, then re-run finish``. That reason goes through `merge_landing_failed`, so M15.40's undo
  removes the bookkeeping commit.
- **Milestone-rollup landing is out of scope.** `milestone_rollup_git.py` is identical to its base
  version again: the first pass's change to it was reverted.
- The merge commit message gets one extra paragraph, naming the graph files resolved, only when some
  were.

## Touch zones (final)

- `specy_road/finish_land_deterministic.py`
- **`specy_road/finish_land_roadmap_graph.py` (new module; please add it to the zones).**
  `sr/constraints/file-limits.yaml` caps toolkit files at 400 lines, and keeping this code inside
  `finish_land_deterministic.py` would have taken it to 519.
- `tests/test_finish_land_deterministic.py`
- `specy_road/milestone_rollup_git.py`: in the zones, but left unchanged (out of scope).

## Quality checks

- C901 compared with the base: `merge_feature_deterministically` 10 → 10,
  `resolve_deterministic_paths` 2 → 2, `_commit_message` 1 → 1. No new function is above 4.
- `ruff check` is clean, no line is over 100 characters, and `specy-road file-limits` passes.

## Verification

- `python -m pytest -q tests/test_finish_land_deterministic.py`: 14 passed.
- `python -m pytest -q -n 4`: 4990 passed, 1 failed.
  - The failure was `tests/test_review_usage.py::test_delegate_after_prompt_cli_does_not_append_to_the_old_log`.
  - That code is unrelated to this change, and the file passes on its own (10 passed).
  - It looks like a flake under parallel load. `ready`'s rerun below records the exit.
- Red-green: with the base `finish_land_deterministic.py` restored, all four new parametrized cases
  fail.

Estimated net line change (informational, not a gate): about +260 package lines, +110 test lines.

## Added

- `finish_land_roadmap_graph.py` (new module): holds the graph-conflict logic so that
  `finish_land_deterministic.py` stays under the 400-line cap.
- `BOOKKEEPING_SUBJECT`: identifies this run's bookkeeping commit at the tip, so its status flip is
  not counted as authored.
- `_EMPTY_TREE`: what a root commit is compared against, so the walk never fails on one (guard).
- `is_roadmap_graph_path`: states once which paths are graph files (`roadmap/**.json`).
- `split_conflicts`: separates graph conflicts from stray ones, aware of the project prefix.
- `_blob`, `_changed`, `_authored_in`, `branch_roadmap_edits`: the first-parent provenance rule
  from the plan review.
- `own_roadmap_edit_refusal`: the one-line A2 reason, naming the files and the next command.
- `take_integration_graph`: resolves each conflicted graph file to integration's version. A path
  integration removed is removed here too (guard).
- `_finished_node_key`, `_changed_graph_paths`, `_nodes_in`: find the finished node's `node_key`
  from the bookkeeping commit.
- `_complete_again`: applies completion by `node_key` and recomputes ancestors (guard: a node that
  is missing or already Complete is left alone).
- `resolve_graph` / `GraphResolveError`, plus `_resolve_graph` in the deterministic module: the
  entry point, with its error mapped to `DeterministicResolveError`.
- `resolvable_conflict`: the classify-or-refuse step, which keeps
  `merge_feature_deterministically` at its base complexity.
- `_graph_note`: the commit-message paragraph, as a helper so `_commit_message` keeps its
  complexity.
- `resolve_deterministic_paths(graph_paths=, bookkeeping=)`: new keyword arguments; the defaults
  keep the old behaviour.
- Test `test_a_roadmap_chunk_conflict_lands_only_when_the_branch_inherited_it`: A3 plus the plan
  review's cases. It runs `finish-this-task` end to end in merge mode after integration moved the
  node, with four parameters:
  - `inherited-only`: lands with Complete, integration's move, the inherited goal, the claim
    released, and `export --check` / `digest --check` clean.
  - `own-commit`: refused.
  - `own-merge-resolution`: refused.
  - `own-edit-not-conflicting`: lands, and the branch's manifest edit is kept.
  - Each refusal case checks for one error line naming the chunk and `git merge dev`, the branch at
    its pre-finish commit, and origin unchanged.
- Test helpers `_chunk_commit` and `_merge_dev_resolving_by_hand`: build the authored and inherited
  histories for that test.
- Mocks: none.
