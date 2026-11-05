# Implementation summary: M21.1 `move-node-chosen-id`

Code commits: `d8dab874` (round 0) and `805f7100` (fix round 1, after merging `origin/WIP/improvements-0-3-1` as `cc575984`) on `feature/rm-move-node-chosen-id` (base `d7d5d1ac`).

## What changed, by acceptance item

- **A1 (CLI):** `move-node` takes `--id NEW_ID` and `--fill-gaps`. `move_node` applies one rule before it loads anything: at most one id form (`--id`, `--fill-gaps`, `--renumber-outline`) per move. The CLI exits 1 and prints the reason; nothing is written. `--id` is checked by `check_chosen_child_id`: it must match `^M[0-9]+(\.[0-9]+)*$`, be the parent plus one numeric segment (`Mk` at the root), and be absent from every node outside the moved subtree. `--fill-gaps` uses `lowest_free_child_id`: children from 1, the root from 0 when any node is `M0` (decided from the whole graph, the moved node included), else 1. The moved subtree's ids count as free, so moving `M0` at the root keeps `M0`. Both forms renumber only the moved subtree through the existing `assign_subtree_ids_inplace`.
- **A2 (one implementation):** `move_node`'s default is now `renumber_outline=False`. `move_node_outline`, `apply_indent` and `apply_outdent` pass `renumber_outline` through, default False. `/outline/move` also forwards `new_id` and `fill_gaps`. `reorder_siblings` sets `sibling_order` only and commits through `stage_id_rewrite`, so one `AtomicWritePlan` is validated before anything is written. With `renumber_outline=True` it renumbers the whole outline and commits through the same plan, which now also rewrites touch-zone and claim-zone segments, as `move-node --renumber-outline` does. Indent and outdent take an optional `OutlineShiftBody`; an omitted body means `renumber_outline=false`.
- **A3 (add-node):** I removed `_canonical_ids_after_add`. The new node keeps `next_child_id` (the next free id under its parent), or an optional `AddNodeBody.new_id` that `check_chosen_child_id` validates (400 if refused). No other node's id changes.
- **A4 (contract):** The new `tests/test_gui_outline_contract.py` pins these response bodies:
  - move and reorder: `{ok: "true"}`
  - indent and outdent: `{ok: true, changed}`, tested with no body, `{}` and an explicit body
  - delete: `{ok: "true", node_id}`
  - add: `{ok: "true", id}`
  - unknown node or node_key: 400
  - other refusals: 400 with a string detail

  It also checks which ids each form changes. The CLI cases are in `tests/test_move_node_subtree.py`: `--id` taken, malformed, lowercase, wrong parent, too deep, with `--fill-gaps`, with `--renumber-outline`, `--fill-gaps` with `--renumber-outline`, plus `--id`, `--fill-gaps` and a subtree `--id` that succeed.
- **A5 (docs):** The "Reordering and reparenting" step 2 and the hand-editing note in `docs/roadmap-authoring.md` now say which ids each CLI and GUI form changes. `renumber_outline: true` is documented for move, reorder, indent and outdent only. Add always preserves every existing id and has no such option. `gui/pm-gantt` is not edited.

## Behaviour changes to flag for review

- **Unknown node is now 400 everywhere (A4).** Before this change, `POST /nodes/{id}/indent` returned 200 `{changed: false}` for an unknown id, `/outdent` returned 500 (a `KeyError`), and `POST /nodes/add` with an unknown `reference_node_id` returned 404. `apply_indent` and `apply_outdent` now raise `ValueError` for an unknown id, and the route maps it to 400. Add-node's 404 is now 400 with the same detail text. No existing test asserted the old codes, and `gui/pm-gantt/src/api.ts` does not branch on 404.
- **Existing test expectations moved under the opt-in.** `tests/test_sync_planning_outline.py::test_reorder_siblings_syncs_planning_files` asserted that reorder renumbers, which A2 reverses. Its assertions are unchanged under the new name `test_reorder_siblings_with_renumber_outline_syncs_planning_files` and now pass `renumber_outline=True`. A sibling test covers the new default: no id changes and no sheet bytes change.

## Touch zones (final list)

These are the brief's zones plus one new file:

- `specy_road/bundled_scripts/roadmap_id_rewrite_staging.py` **(new; please add it to the zones).** With the effective cap of 400 lines/file in `sr/constraints/file-limits.yaml`, `roadmap_move_node.py` would have reached 436 lines. I moved `_stage_merged_nodes`, `_stage_planning_moves`, `_rewrite_touch_zones` and `_stage_registry_ids` into this module verbatim, keeping their names. `stage_id_rewrite` stays in `roadmap_move_node.py` because the existing rollback test patches `roadmap_move_node.run_validate_raise`.

`specy_road/bundled_scripts/roadmap_gui_tree.py` (outside the zones) is unchanged: the unknown-node guard sits in `apply_indent` and `apply_outdent` instead.

## Verification

- `python -m pytest -q -n 4 -p no:cacheprovider`: 5032 passed at round 0; 5064 passed after the merge and fix round 1.
- `python -m ruff check specy_road tests scripts`: clean.
- `python -m specy_road.cli file-limits`: OK.
- `validate`, `export --check` and `digest --check` on the dogfood fixture: exit 0.

## Fix round 1 (review `gpt-6.1-sol-low` at `dc686e3a`)

- **Finding 1, root numbering base.** Class: a project-wide fact (the root base, `M0` vs `M1`) derived from a set that already excluded the moved subtree. The fix is one rule, `_first_child_number`, which reads the whole graph. Both root allocators use it: `lowest_free_child_id` (`--fill-gaps`) and `next_free_child_id` (the default). The default had the same flaw: moving the only root `M0` back to the root gave `M1`.
- **Finding 2, docs.** Class: a doc sentence grouping add with the operations that take `renumber_outline`. Step 2 now limits `renumber_outline: true` to move, reorder, indent and outdent, and says add preserves existing ids. I checked every other `renumber_outline` mention in docs, docstrings, model comments and help.
- **Maintainer refactor rule.** In round 0, `move_node` had two refusal branches and `apply_indent` / `apply_outdent` one unknown-node branch each, making them more complex than at the merge base. Now:
  - The refusals are one rule, `_refuse_id_form_combinations`: at most one id form. The CLI message names the forms given and says "mutually exclusive"; I updated my own refusal test's expected text to match.
  - The unknown-node guard is one helper, `_load_with_node`, shared by indent and outdent.
  - Measured with ruff C901 at `max-complexity=1`, no function that exists at the merge base is now more complex. The pre-existing `noqa: C901` on `_api_add_node_impl` is unchanged, and so is that function's complexity.

## Probes

- `lowest_free_child_id(["M0","M2"], root, ignore={"M0"})`: `M0` (was `M1`). Unit param added.
- `lowest_free_child_id(["M0","M1"], root, ignore={"M0"})`: `M0`. Unit param added.
- `next_free_child_id(["M0"], root, exclude M0)`: `M0` (was `M1`, same class). Unit test added.
- `next_free_child_id(["M0","M1"], root, exclude M0)`: `M2`; `(["M1"], exclude M1)`: `M1`. The non-`M0` base is unchanged.
- CLI: `move-node M2 --to-parent null --id M0`, then `move-node M0 --to-parent null --fill-gaps`: exit 0 and no id changes (`M0` keeps `M0`; `M2.4` became `M0.4`, then stayed).
- Pre-fix code (`git archive` of the merge commit with the new tests copied in): the 3 new `M0` cases fail; on the fix they pass.
- `check_chosen_child_id`: does not use the base (free = absent outside the subtree), so the class does not reach it. `--id M0` at the root is accepted when `M0` is free or is the moved node.
- `renumber_display_ids_inplace`: its base comes from the full roots list, so the class does not reach it. No change.
- GUI add-node (`roadmap_layout.next_child_id`, outside the zones): it filters nothing, so the class does not reach it. No change.
- `subtree_ids`: computed from the full graph. Not affected.
- Docs, docstrings, `gui_app_models.py` comments and CLI help: no other text attributes `renumber_outline` to add.
- Complexity (ruff C901 at `max-complexity=1`, base `d7d5d1ac` against tip): no base function grew; `move_node` is 4 (base 4) and `apply_indent` / `apply_outdent` are 3 (base 3).
- Targeted suites: 200 passed. Full suite after the merge: 5064 passed. ruff on `specy_road tests scripts` is clean, and `file-limits` is OK.

## Added

### Helpers
- `roadmap_outline_renumber.DISPLAY_ID_RE`: the A1 id regex, shared by the check and its error text.
- `roadmap_outline_renumber.subtree_ids`: the moved subtree's ids, which "free" and "lowest gap" ignore (A1).
- `roadmap_outline_renumber.lowest_free_child_id`: `--fill-gaps` / `fill_gaps`, including the start rule at the root (A1).
- `roadmap_outline_renumber.check_chosen_child_id`: validates `--id`, GUI `new_id` and add-node `new_id` (A1, A3).
- `roadmap_move_node.stage_id_rewrite`: one stage-and-commit path for `move_node` and `reorder_siblings`, so reorder is atomic (A2).
- `roadmap_move_node._moved_node_id`: picks next-free, fill-gaps or chosen id; keeps `move_node` under the function cap (A1).
- `roadmap_move_node._refuse_id_form_combinations`: the one "at most one id form" refusal rule (A1; fix round 1 consolidation).
- `roadmap_outline_renumber._first_child_number`: the one root-base rule (`M0` from the whole graph) for both allocators (fix round 1, finding 1).
- `roadmap_outline_ops._load_with_node`: shared indent/outdent load with the unknown-node guard (A4; fix round 1 consolidation).
- `roadmap_id_rewrite_staging.py`: existing staging helpers moved verbatim for the file cap (no new logic).
- `gui_app_models.OutlineShiftBody`: optional indent/outdent body carrying `renumber_outline` (A2).
- `MoveOutlineBody.new_id`, `MoveOutlineBody.fill_gaps`, `MoveOutlineBody.renumber_outline`, `ReorderBody.renumber_outline`, `AddNodeBody.new_id`: optional request fields (A2, A3).

### Branches and guards
- `move_node`: refuses more than one of `new_id`, `fill_gaps`, `renumber_outline`, through `_refuse_id_form_combinations` (A1).
- `apply_indent` / `apply_outdent`: unknown node id raises `ValueError` (through `_load_with_node`), so the route returns 400 instead of 200 or 500 (A4).
- `_api_add_node_impl`: validates a requested `new_id` and returns 400 if refused (A3).
- `_api_add_node_impl`: unknown reference returns 400 instead of 404 (A4).
- `reorder_siblings`: renumbers only under `renumber_outline` (A2).

### Mocks
- none (the existing `run_validate_raise` monkeypatch is reused by the parametrized rollback test).

### Tests
- `tests/test_gui_outline_contract.py` (new): pins the endpoint request/response shapes and which ids each GUI form changes (A2, A3, A4).
- `tests/test_move_node_subtree.py::test_a_move_can_take_a_chosen_or_lowest_free_id`: `--id`, `--fill-gaps` and subtree `--id` cases (A1, A4).
- `tests/test_move_node_subtree.py::test_a_bad_chosen_id_is_refused_and_writes_nothing`: each CLI refusal exits 1, names the reason and writes nothing (A1, A4).
- `tests/test_outline_renumber.py::test_lowest_free_child_id`: lowest-gap and root-start rules, including a moved `M0` (A1; fix round 1 params).
- `tests/test_outline_renumber.py::test_next_free_root_id_when_the_moved_node_is_left_out`: the default allocator keeps the `M0` base (fix round 1, same class).
- `tests/test_move_node_subtree.py::test_moving_m0_at_the_root_with_fill_gaps_keeps_m0`: CLI regression for finding 1.
- `tests/test_move_node_cli.py::test_a_rejected_move_leaves_the_working_tree_untouched`: parametrized to add reorder, the atomicity regression (A2).
- `tests/test_sync_planning_outline.py::test_reorder_siblings_changes_only_sibling_order_by_default`: reorder's new default (A2). The existing renumber test now passes `renumber_outline=True`.
