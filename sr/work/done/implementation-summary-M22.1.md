# Implementation summary: M22.1 `group-into-member-id`

## What changed

- `specy_road/bundled_scripts/roadmap_outline_group.py`
  - `group_nodes`: the free-id check passes the listed nodes' ids as `ignore_ids`
    (was the empty set). A descendant's id still fails the direct-child rule with
    today's message; an id held by any other node still fails "already taken".
  - The new parent is inserted under a transient id from `_transient_parent_id`: a direct
    child id of the common parent that is no node's id and no prefix of one, wherever that
    node hangs (fix round 1, below). Members move under it
    as `<transient>.1..N`. The planning sheet is planned for `NEW_ID` before the transient
    id is set, so sheet path and text never see it.
  - `NewParent` gains `final_id` and `finish(nodes)`, which runs
    `assign_subtree_ids_inplace(nodes, node_key, final_id)`: the parent and its whole
    subtree take their final ids in one step on the final topology.
  - `--into-new` help: "a direct child id of the siblings' parent, free or held by one of
    the listed nodes."
- `specy_road/bundled_scripts/roadmap_move_node.py`: `move_nodes` calls
  `new_parent.finish(nodes)` after the last move, before the old -> new map, scope and
  staging are computed. Docstring updated. Plain `move-node` (no `new_parent`) is unchanged.
- `roadmap_outline_ops.py` and `roadmap_outline_renumber.py` are unchanged.
- `docs/roadmap-authoring.md`: the group-nodes rule says NEW_ID may be held by a listed node.
- `CHANGELOG.md`: `[Unreleased]` / Fixed entry.

The transient id is used on every group, so there is one code path. When `NEW_ID` is free
and equals the next free id, `finish` changes nothing.

## Touch zones

Confirmed as listed. No change was needed outside them. `roadmap_apply_entries.py` and
`gui_app_routes_nodes.py` call `group_nodes` with the same signature and are unchanged.
The new code fits within the existing modules, and file limits are OK.

## Test change to note

`tests/test_outline_group_cli.py::test_a_refused_group_leaves_the_tree_byte_for_byte_unchanged`
had an `own-id` row (`--into-new M1.1 M1.1` refused "already taken"). A1 deliberately
reverses exactly that behaviour, so the row is replaced by the A2 `descendant-id` row
(`--into-new M1.2.1 M1.2` refused "not a direct child id of M1", tree byte-for-byte unchanged).

## Fix round 1 (review `gpt-5.6-sol-high` at 89107f32)

- **Finding class:** the transient id was chosen among the parent's direct children only
  (`next_free_child_id`). An edge-only re-parent keeps a node's id, so a valid graph can
  hold `M1.3` (and its child `M1.3.4`) under `M2`. The transient then equalled `M1.3`, and the
  final id step absorbed `M1.3.4` as `M1.1.4`, which failed validation.
- **Design fix (removes the class):** one rule, `_transient_parent_id`: one past the highest
  first segment among every id that starts `<parent_id>.` (`M` at the root), wherever its node
  hangs. The transient is therefore neither an existing id nor a prefix of one, and neither
  is any `<transient>.k` the members take. It replaces the `next_free_child_id` call; no
  branch was added.
- **Regression:** `test_group_transient_id_names_no_existing_node`. M1.3 is under M2 with child
  M1.3.4 (the fixture validates). Grouping M1.1 and M1.2 into M1.1 succeeds, and M1.3 and
  M1.3.4 keep their ids and parent. It failed before the fix with the reviewer's error.
- Merged `origin/WIP/improvements-0-3-1` first (clean, roadmap bookkeeping only).

## Probes

- Reviewer's topology (M1.3 + M1.3.4 under M2, group M1.1 M1.2 into M1.1): failed before the fix (`M1.1.4` sheet name); passes after, M1.3 subtree unchanged.
- Root transient (`parent_id` None, prefix `M`): with M1 and M2 at the root it is `M3`. Grouping M1 and M2 into M1 (phase) succeeds with the full chained map.
- Members' own renumbering (`_apply_move` → `assign_subtree_ids_inplace`) builds children by `parent_id`, and ids are unique in a valid graph, so a twin id elsewhere is never pulled in. The only shared-id case was the transient, now excluded.
- Moves' `--id` check on `<transient>.k`: no id starts with `<transient>.`, so it is always free.
- Final ids colliding with a same-id node hanging elsewhere (stray `M1.2.3` under M2, group into `M1.2`): refused by validation, `duplicate ids: ['M1.2.3']`, tree byte-for-byte unchanged. The same happens with a free NEW_ID (`M1.5` with stray `M1.5.3`), which is behaviour from before this leaf. A1 requires no collision only with a member's descendant; validation keeps every other collision fail-closed.
- `ruff check --select C901` on the module: clean. No function is more complex than at the merge base. `group_nodes` lost no branch and gained none.

## Verification

- `pytest -n 4 tests/test_outline_group_cli.py tests/test_gui_outline_contract.py`: pass
- PM GUI Python API tests (`tests/test_gui_app*.py`, `tests/test_roadmap_gui_*.py`), plus
  `tests/test_move_node_cli.py` and `tests/test_rename_refs.py`: pass, unchanged (221 in that run)
- Full suite `pytest -n 4`: 6187 passed (round 0)
- Fix round 1: the targeted tests (CLI, GUI contract, GUI API, move-node, rename-refs, apply): 253 passed; `ruff check specy_road tests scripts`: clean; file-limits: OK
- `specy-road file-limits`: OK. `ruff check` on the changed Python: clean
- Red-green: with the package changes stashed, both new CLI cases fail
  (`id 'M1.2' is already taken by another node`), exit 1
- A6: there is no `tests/parity/` in this tree, so the golden rule does not apply

## Added

- `NewParent.final_id` field: the id the new parent takes after the moves (`into_new`).
- `NewParent.finish()` method: gives the parent's subtree its final ids in one step (A1).
- `move_nodes` branch `if new_parent is not None: new_parent.finish(nodes)`: runs that step after the last move.
- Helper `_transient_parent_id` (fix round 1): a parent id that is no node's id nor any id's prefix, so members cannot collide while they move (A1).
- Test `test_group_into_an_id_a_listed_node_holds[plain|rewrite-refs]` (CLI test file, run in-process
  through `roadmap_outline_group.main`): the A2 chained case. It checks the printed map without the
  new parent, sheets, the claim on M1.2 -> M1.2.2, validation exactly once, prose with and without
  `--rewrite-refs`, and that the transient id M1.4 appears in no id, path, file content or output.
  It counts `validate_at` with a monkeypatch, as the existing ten-siblings test does.
- Test `test_group_transient_id_names_no_existing_node` (fix round 1): a valid graph with M1.3 + M1.3.4 under M2 stays unchanged after grouping into M1.1.
- Parametrize row `descendant-id` (replaces `own-id`): A2's descendant-id refusal, byte-for-byte unchanged.
- Test `test_outline_group_into_an_id_a_listed_node_holds` (GUI contract): A3's case for this input through `POST /api/outline/group`.
