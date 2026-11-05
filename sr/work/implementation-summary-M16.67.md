# Implementation summary: M16.67 `move-node-keeps-other-ids`

## What changed

- **`specy_road/bundled_scripts/roadmap_outline_renumber.py`**: new
  `next_free_child_id(nodes, parent_id, *, exclude_key=None)`: one past the
  highest numbered child of the parent (root = `M<n>`). Gaps are allowed and
  never closed; the moved node is left out of the count. Also new
  `assign_subtree_ids_inplace(nodes, moved_key, new_id)`: gives the moved node
  `new_id`, and each descendant keeps its own last segment under its parent's
  new id (`M1.2.4` → `M2.5.4`). Returns `old -> new` for the subtree only.
  `renumber_display_ids_inplace` is unchanged. The module docstring now names
  both forms.
- **`specy_road/bundled_scripts/roadmap_move_node.py`**: `move_node` gains a
  keyword `renumber_outline: bool = True`.
  - `True` is today's whole-outline renumber. That default keeps the PM GUI's
    `roadmap_outline_ops.move_node_outline` call (positional, outside the
    zones) and its drag behaviour unchanged (A2, out of scope per A4).
  - `False` uses the two new helpers. The CLI passes
    `renumber_outline=args.renumber_outline`, so plain `move-node` renumbers
    only the moved subtree and `--renumber-outline` gives the old behaviour (A1, A2).
  - Planning-sheet renames are planned only for the renumbered nodes, so an
    unrelated sheet whose path was already off-pattern is not swept into the
    move. In outline mode that is still every node, as before.
  - Registry `node_id` and touch-zone rewrites use the same `old -> new` map,
    staged through the existing `AtomicWritePlan` (A3).
  - The module docstring, parser description, the new `--renumber-outline`
    help and the `--index` help say which ids each form changes.
- **`docs/roadmap-authoring.md`**:
  - "Supported workflow" item 2 now documents `move-node`: subtree-only by
    default, the next-free rule with gaps, descendants keeping their
    segments, what `--index` does, and that `--renumber-outline` and the PM
    UI drag renumber the whole outline. It also says which ids each form
    changes, the atomic sheet, zone and claim rewrites, and that `renumbered`
    history events appear only for changed ids.
  - The existing "Renumber display ids" text is kept verbatim in the same
    item. I merged the two items because the file was at its 400-line cap
    (`specy-road file-limits`), and the later items were renumbered.
  - The hand-editing note (line ~364) names both forms.

## Acceptance

- **A1**: the default mode changes ids only inside the moved subtree. Sheets
  and registry `node_id`s change only for renamed ids. Touch-zone text
  changes only where a whole path segment equals a moved node's old id, so a
  zone keeps naming the node it named. That is the "touch-zone references"
  rewrite A3 keeps "as today", on any node or claim. A zone naming a
  non-moved node never changes, because only subtree ids are in the map.
  I read A1's "touch-zone text" as text tied to a non-moved node's id. If the
  reviewers read it as "never rewrite another node's reference to a moved
  id", the fix is one line: filter the nodes passed to `_rewrite_touch_zones`.
- **A2**: `--renumber-outline` is the only CLI path to the whole-outline
  renumber. The GUI's call path is unchanged.
- **A3**: one atomic plan, as before. History events come from graph diffs
  (`history_events.diff_snapshots`), so `renumbered` appears only for nodes
  whose id changed. A test asserts this.
- **A4**: see the tests below.

## Touch zones

The zones were accurate. `roadmap_outline_ops.py`, `roadmap_gui_tree.py` and
`gui_app_routes_nodes.py` are unchanged; they keep the outline renumber
through `move_node`'s default. `specy_road/cli_usage.py:46` (outside the
zones) still reads "re-parent a subtree and renumber display ids". That is
still true and I did not change it; the argparse help carries A2's
per-form wording. No new module was needed.

## Verification

- `python -m pytest -n 4 -q`: 4915 passed.
- `specy-road validate --repo-root tests/fixtures/specy_road_dogfood`: exit 0.
- `specy-road file-limits`: OK.
- `ruff check` on the changed Python files: clean.
- Red-green: with the production change reverted, the new and adjusted tests
  in `tests/test_move_node_cli.py` fail (5 failed, 9 passed).

## Added

- `next_free_child_id` (roadmap_outline_renumber.py): A1's next-free id with gaps allowed.
- `_numeric_last_segment` (roadmap_outline_renumber.py): parses a child's number under a prefix for `next_free_child_id`, and ignores non-numeric ids.
- `assign_subtree_ids_inplace` (roadmap_outline_renumber.py): A1's subtree-only renumber.
- `renumber_outline` keyword and its branch in `move_node`: A2's choice between the two forms. The default `True` keeps the GUI path unchanged.
- Sheet planning limited to `renumbered` nodes in `move_node`: A3, the rewrites are limited to the renamed set.
- `--renumber-outline` CLI flag: A2.
- Mocks: none.
- Test `test_moving_a_leaf_out_of_the_middle_of_a_milestone` (parametrized subtree-only / renumber-outline): A4, siblings and other milestones keep their ids, sheets and claims. The flag reproduces today's behaviour.
- Test `test_a_subtree_move_renumbers_only_its_descendants`: A4 subtree case, plus A3's sheet renames and `renumbered` history events limited to the subtree.
- Test `test_a_claimed_moved_leaf_keeps_its_claim_under_the_new_id`: A4, the claim follows the moved leaf and other claims keep their ids.
- Test helpers `_wide_fixture`, `_ids`, `_sheets`, `_unchanged_except` (tests/test_move_node_cli.py): the graph with gaps and nesting that the new tests need, and the comparisons they share.
- Changed tests:
  - `test_touch_zone_segments_naming_an_old_id_follow_the_node` (tests/test_move_node_cli.py) and `test_move_node_keeps_the_scaffold_m1_numbering` (tests/test_prerelease_apps.py) now pass `--renumber-outline`, with every assertion unchanged.
  - Both pin whole-outline behaviour: the `M2.1 -> M2.2` chain and the scaffold's M1 root base. A2 and A4 put that behaviour behind the flag.
