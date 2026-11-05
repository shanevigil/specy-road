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
  - Registry `node_id` and touch-zone rewrites use the same subtree-only
    `renamed` map and are staged through the existing `AtomicWritePlan` (A3).
    `_stage_registry_ids` takes the keyword `claims_in_map_only`. When it is
    set, only claims whose `node_id` is in the map are rewritten at all,
    zones included.
  - The module docstring, parser description, the new `--renumber-outline`
    help and the `--index` help say which ids each form changes.
- **Tests moved:** `tests/test_move_node_cli.py` passed its 400-line cap in
  fix round 1. The M16.67 tests moved to the new
  **`tests/test_move_node_subtree.py`**, and the shared fixture, runner and
  helpers moved to the new public **`tests/move_node_helpers.py`**. The names
  were renamed without the leading underscore so no test imports a
  `_`-prefixed name. Tests that already existed at the base stay in
  `test_move_node_cli.py` with the same names and assertions; only their
  helper calls were renamed. A few lines were wrapped where the longer
  helper names pushed them past 100 characters.
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

- **A1**: the default mode changes ids only inside the moved subtree. Fix
  round 1 (grok-4.7-low): every rewrite step now uses one id map built from
  the subtree (`renamed`) and one node scope. In subtree mode the scope is
  the subtree's nodes, plus the registry claims whose `node_id` is in the
  map. Touch-zone text, sheet renames, registry `node_id` and claim zones are
  all limited to that scope. Another node's or claim's zone that names a
  moved id is left as written. `--renumber-outline` keeps the global scope.
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

## Probes

Finding class: a rewrite step reaching nodes or claims outside the moved
subtree in subtree mode.

- Node touch-zone text outside the subtree (whole segment `docs/M1.2/`, bare
  `M1.2.2`, substrings `src/M1.2.2x/` and `notes/M1.2-old.md`, and a zone on
  M2 naming `M1.2.4`): unchanged. Covered by
  `test_a_subtree_move_rewrites_nothing_outside_the_subtree`, which fails on
  12520342.
- Registry claim outside the subtree whose zone names a moved id
  (`alpha-work`, `docs/M1.2/`): `node_id` and zones unchanged (same test).
- The subtree's own zones and claim: they follow the new ids, while a zone
  inside the subtree that names a non-moved id (`docs/M1.3/`) stays (same
  test).
- Planning-sheet renames and contents outside the subtree: names and bytes
  unchanged (same test). `_stage_planning_moves` copies sheet text verbatim
  and never edits contents.
- Registry `node_id` of claims outside the subtree: the map holds subtree ids
  only, so these are unchanged
  (`test_a_claimed_moved_leaf_keeps_its_claim_under_the_new_id`).
- History `renumbered` events: derived from graph diffs, and only subtree ids
  change (`test_a_subtree_move_renumbers_only_its_descendants`).
- Identity move (last child moved back under the same parent): before this
  round the registry was re-dumped with no change. Now the map is empty, so
  the file stays byte-identical. Probed by script: exit 0, id stays M1.3,
  registry bytes equal.
- `dependencies` and other text fields (acceptance, notes): never rewritten
  by `move_node`, since dependencies are node_keys (read the code).
- `sibling_order` of the old parent's other children: re-packed with order
  kept, as before. This is not an id, zone, sheet or claim, so it is left as
  it was, and the new test compares id, parent_id, touch_zones and
  planning_dir.
- Chunk files: `_stage_merged_nodes` re-stages every chunk, as before. The
  content outside the subtree differs only by `sibling_order`.
- `--renumber-outline`: still rewrites globally
  (`test_touch_zone_segments_naming_an_old_id_follow_the_node`, unchanged
  assertions).

## Verification

- `python -m pytest -n 4 -q`: 4915 passed (first round).
- Fix round 1: targeted tests `tests/test_move_node_cli.py`,
  `tests/test_move_node_subtree.py`, `tests/test_prerelease_apps.py`,
  `tests/test_outline_renumber.py` and
  `tests/test_cli_imports_without_gui_extra.py`: 30 passed.
- `specy-road validate --repo-root tests/fixtures/specy_road_dogfood`: exit 0.
- `specy-road file-limits`: OK.
- `ruff check` on the changed Python files: clean.
- Red-green: with the production change reverted, the new and adjusted tests
  in `tests/test_move_node_cli.py` fail (5 failed, 9 passed). Fix round 1: on
  12520342's production code the new outside-the-subtree test fails (1 failed,
  14 passed), and it passes with the fix.

## Added

- `next_free_child_id` (roadmap_outline_renumber.py): A1's next-free id with gaps allowed.
- `_numeric_last_segment` (roadmap_outline_renumber.py): parses a child's number under a prefix for `next_free_child_id`, and ignores non-numeric ids.
- `assign_subtree_ids_inplace` (roadmap_outline_renumber.py): A1's subtree-only renumber.
- `renumber_outline` keyword and its branch in `move_node`: A2's choice between the two forms. The default `True` keeps the GUI path unchanged.
- Sheet planning limited to `renumbered` nodes in `move_node`: A3, the rewrites are limited to the renamed set.
- `--renumber-outline` CLI flag: A2.
- `claims_in_map_only` keyword on `_stage_registry_ids` (fix round 1): limits claim rewrites to the subtree's claims in subtree mode.
- `scope` / single `renamed` map in `move_node` (fix round 1): one subtree-only input to every rewrite step, which removes the finding's class.
- Mocks: none.
- Test `test_moving_a_leaf_out_of_the_middle_of_a_milestone` (parametrized subtree-only / renumber-outline): A4, siblings and other milestones keep their ids, sheets and claims. The flag reproduces today's behaviour.
- Test `test_a_subtree_move_renumbers_only_its_descendants`: A4 subtree case, plus A3's sheet renames and `renumbered` history events limited to the subtree.
- Test `test_a_claimed_moved_leaf_keeps_its_claim_under_the_new_id`: A4, the claim follows the moved leaf and other claims keep their ids.
- Test `test_a_subtree_move_rewrites_nothing_outside_the_subtree` (fix round 1): A1 regression. Zones (including substrings of a moved id), sheets and claims outside the subtree stay as written.
- `tests/move_node_helpers.py` (fix round 1): shared public helpers (`base_fixture`, `wide_fixture`, `run_move_node`, `nodes_by_key`, `set_zones`, `ids_by_key`, `sheet_names`, `unchanged_except`, node-key constants), moved from `test_move_node_cli.py` so the split test files share one fixture.
- `tests/test_move_node_subtree.py` (fix round 1): holds the four M16.67 tests, because `test_move_node_cli.py` hit the 400-line cap.
- Changed tests:
  - `test_touch_zone_segments_naming_an_old_id_follow_the_node` (tests/test_move_node_cli.py) and `test_move_node_keeps_the_scaffold_m1_numbering` (tests/test_prerelease_apps.py) now pass `--renumber-outline`, with every assertion unchanged.
  - Both pin whole-outline behaviour: the `M2.1 -> M2.2` chain and the scaffold's M1 root base. A2 and A4 put that behaviour behind the flag.
