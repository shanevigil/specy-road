# M22.50 — finish keeps Complete when the same roadmap chunk conflicts

A nested project root made `git ls-tree` print roadmap paths relative to that directory. `_graph_paths_at` kept only names starting with the project prefix (`sr/`), so the list was empty, `_finished_node_key` returned None, and `_complete_again` never ran. The landing still took the integration side of the chunk and the merge message still said the Complete status was applied. Reproduced through `finish-this-task` before the fix: the leaf landed `In Progress` (the integration side's status in this fixture), with the integration `sibling_order` and the other node's `touch_zones`. It did not land Complete, so the fix stayed inside the zones.

`ls-tree --full-name` returns git-root paths, the prefix filter keeps them, and `git show <commit>:<path>` finds the leaf by `node_key`. The resolved chunk is the integration side with that leaf set to Complete. Ancestors still go through `complete_rolled_up_ancestors`. When the bookkeeping commit is known and the leaf is still in the graph but not Complete, `resolve_graph` raises `GraphResolveError` and the merge is aborted before the commit, so nothing is pushed. The error names the chunk and the codename. A leaf the integration side removed stays absent. The merge message adds "finish's Complete status was applied again" only when that leaf is Complete in the resolved graph.

Touch zones, confirmed and unchanged: `specy_road/finish_land_roadmap_graph.py`, `specy_road/finish_land_deterministic.py`, `CHANGELOG.md`, `tests/test_finish_land_roadmap_graph.py`. `resolve_deterministic_paths` still returns the paths to stage, so `specy_road/milestone_rollup_git.py` and the other callers stay as they are.

`python -m pytest tests/test_finish_land_roadmap_graph.py -q --tb=short` passed (9 tests).

## Added

### Helpers

- `_landed_leaf`: finds the finishing leaf in the resolved worktree, by `node_key` when this run has one and by codename when the bookkeeping commit's parent registry has no row.
- `_require_reapplied`: aborts the merge when that leaf is still present and not Complete, naming the chunk and the codename.
- `leaf_landed_complete`: tells the merge message whether the finishing leaf is Complete after resolution.

### Branches or guards

- `_graph_paths_at` passes `ls-tree --full-name`, so a nested project root's roadmap paths are git-root-relative and survive the prefix filter.
- `resolve_graph` skips the re-apply when there is no bookkeeping commit, and calls `_require_reapplied` when there is one.
- `_graph_note` appends the Complete-status sentence only when the leaf landed Complete.

### Mocks

none

### Tests

- `_nested_chunk_repo`: a nested merge-mode repository whose chunk holds the finishing leaf and a sibling, for the acceptance table.
- `_diverge_chunk`: the integration side's edit of that chunk after the claim (sibling_order, the other node's touch zones, or removal of the leaf).
- `_hide_claim_from_parent`: commits the registry without the claim and leaves the row only in the worktree, so the bookkeeping commit's parent has no row.
- `test_a_conflicted_chunk_keeps_the_leaf_complete_or_stops`: one table — nested re-apply keeps Complete plus the integration fields and the message claims it; a missing registry row exits non-zero, names the chunk and the codename, and leaves the integration ref unchanged; a removed leaf lands absent and the message does not claim the status was applied.
