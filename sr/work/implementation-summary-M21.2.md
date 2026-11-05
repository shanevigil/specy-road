# M21.2 implementation summary: outline-group-cli

## What changed

- `move_nodes(root, moves, *, renumber_outline, new_parent)` in `roadmap_move_node.py`: every move runs in memory, then one `stage_id_rewrite` stages one `AtomicWritePlan` and validates once. `move_node` is a one-move call, and `move_node_outline`, so `apply_indent` / `apply_outdent`, go through it.
- `apply_indent` / `apply_outdent` / `move_node_outline` now return the `old -> new` map (`None` on a no-op) instead of a bool. The GUI routes answer `changed: id_map is not None`, so their shape is unchanged.
- `specy-road indent`, `outdent`, `group-nodes` and `group_nodes()` in the new `roadmap_outline_group.py`; `POST /outline/group` (`GroupOutlineBody`) calls the same function. Every refusal is a 400 with a string detail, a malformed body and a locked milestone included; only bytes that are not JSON stay FastAPI's 422.
- `docs/roadmap-authoring.md` and `cli_usage` list the commands.

## Touch zones (final list)

The brief's zones, plus one new file: **`specy_road/bundled_scripts/roadmap_outline_group.py`**. `specy-road file-limits` reads `sr/constraints/file-limits.yaml` (400 lines per file, not the root file's 1,000), and the new code took `roadmap_move_node.py` to 653 lines, so per the executor prompt the group and CLI code went to a new module. Please add it to the leaf's zones. `roadmap_move_node.py` is now 394 lines and `cli.py` exactly 400, which is why its three forwarding entries are one `dict.fromkeys` line.

## Decisions for the reviewers

- **One indent no-op message (fix round 1).** `apply_indent` also returns no-op when the sibling above is a gate or the depth cap is hit. The CLI now prints the fixed `no previous sibling` for all of them, as A1 and the review require; help, docs and `_run_shift`'s docstring state the rule: no sibling above can *take* the node. The limit: with a gate above, the words alone do not say why. The GUI keeps `changed: false` for these.
- **Locks on `/outline/group` are 400, not 409 (fix round 1).** A4 says 400 for refused input, so this route differs from its siblings' 409. A client that special-cases 409 on the other routes needs to know.
- **CLI indent also checks the milestone lock on the sibling above**, as `move-node` does for its target. The GUI indent route does not (existing behaviour, left alone).
- **`group_nodes` does no outline-depth check**, the same as `move-node` and `/outline/move`; only indent has one (`MAX_OUTLINE_DEPTH`), and `validate` does not enforce it. A group can therefore exceed 8 segments. Not in the acceptance, so not added.
- **No self-heal before a group** (`add-node` runs one): `move-node` does not either, and a heal would write to the tree before a refusal, breaking "byte-for-byte unchanged".
- **`NewParent.stage` repeats the six lines of manifest handling in `write_with_routing`**, because `roadmap_chunk_router.py` is outside the zones. A shared helper there would remove the copy.
- **`--type gate`** is not a CLI choice; on the GUI it is refused with a 400. An unknown `type` or empty `title` is refused by validation, then rolled back (400), and the route validates the body itself, so none of these is a 422.

## Verification

- Full suite: `python -m pytest -n 4 -q`, 5180 passed.
- `file-limits` passes for `sr/` and for the root constraints.
- Manual run on a scratch copy of the dogfood fixture: group, outdent, indent, the no-op refusal, then `validate` OK.

## Fix round 1

Reviewer `gpt-6.1-sol-low` blocked `3f446e67` on two findings; `origin/WIP/improvements-0-3-1` is merged in.

- **A1, class: an output that differs from the acceptance's fixed no-op text.** Removed the extra branch: `cmd_indent` passes one constant.
- **A4, class: a refusal of `/outline/group` input answered with anything but a 400.** Wider than the finding: every malformed body was a 422. `group_nodes` now owns the lock refusal (a `ValueError`, shared by CLI and GUI), and the route validates the body inside the same `try`. Both separate lock paths (`cmd_group`'s pre-check and the route's `_pm_milestone_lock_guard` call) are gone.

## Probes

- Indent, nothing above (`M1.1`): exit 1, `no previous sibling`, tree unchanged (test).
- Indent, gate above: same no-op and message (test, was the finding).
- Indent, depth cap: same no-op and message (test, not covered before).
- Indent with a locked sibling above: lock refusal, not a no-op message (test). A lock is a refusal with its own text, per the plan review.
- Outdent no-ops: `outdent_parent_id` returns None only at the root, so `already at root` is always true. The later `if not parent_of` in `apply_outdent` is existing code and unreachable.
- Outdent of a gate to where a gate may not sit: `_validate_reparent_target` raises `ValueError`, exit 1 with its own text (read, existing behaviour).
- GUI indent/outdent no-op: still 200 `{"ok": true, "changed": false}` (existing contract test).
- `/outline/group` locked: 409 before, 400 now (test).
- `/outline/group` missing field, empty object, list body, no body, `node_ids` not a list: 422 before, 400 now (probe, then tests).
- `/outline/group` body that is not JSON: still 422, raised before the route runs. Accepted limit, stated in the route docstring.
- `/outline/group` with a corrupt chunk, missing chunk or missing manifest: 412 from the fingerprint check before the route runs, so the old guard's 409 for an unreadable roadmap is not reachable through it (probe).
- Other statuses on the route: 412/428 fingerprint and 403 read-only are request-level, not input refusals; left alone.
- `group_nodes` refusal order: lock check comes after the sibling check and before anything is derived or staged; tree unchanged (tests).

## Added

Helpers and types:
- `NodeMove` (`roadmap_move_node.py`): one move in a batch.
- `_apply_move`: the old `move_node` body, in memory, so a batch can repeat it.
- `move_nodes`: the batch primitive A2 requires.
- `print_id_map` (`roadmap_outline_ops.py`): the map output `cmd_move` already had, now shared by four commands.
- `NewParent` with `insert` / `stage`: puts the group's new node in memory and in the same plan.
- `_common_parent`: refuses non-distinct, unknown or non-sibling ids before staging.
- `group_nodes`: the shared CLI and GUI operation.
- `_shift_target`, `_run_shift`, `cmd_indent`, `cmd_outdent`, `cmd_group`, `_add_shift_parser`, `_add_group_parser`, `build_parser`, `main`: the CLI.
- `_api_outline_group`, `GroupOutlineBody`: the endpoint.

Branches and guards:
- `new_parent` parameter on `stage_id_rewrite` / `move_nodes`: joins the new node to the one plan.
- `decision.is_new_chunk` in `NewParent.stage`: a new chunk needs its manifest entry in the same plan (reached by the root-phase test).
- `self.sheet is not None`: `plan_planning_sheet_for_new_node` returns None when the sheet exists.
- `if not node_ids` in `_common_parent`: reachable from `node_ids: []` on the endpoint.
- `above is not None` in `cmd_indent`: lock check on the new parent.
- `assert_pm_nodes_not_milestone_locked` in `group_nodes`: the one lock refusal for CLI and GUI.

Mocks:
- `run_validate_raise` patched to fail in `test_a_group_that_fails_validation_rolls_everything_back`: forces the rollback, as the existing move test does.
- `validate_at` wrapped to count in `test_grouping_ten_siblings_validates_the_roadmap_once`: A3 requires this count.

Test helpers (`tests/move_node_helpers.py`):
- `run_cli`: runs through the real `specy-road` dispatcher.
- `tree_bytes`: the byte-for-byte comparison.
- `lock_milestone`: sets up lock refusals.

Tests (`tests/test_outline_group_cli.py`):
- `test_a_shift_moves_only_the_subtree_and_prints_the_map`: A1.
- `test_a_shift_with_nothing_to_do_exits_1_and_writes_nothing`: A1 no-ops and unknown ids.
- `test_no_sibling_above_that_can_take_the_node_is_the_same_no_op`: the gate and depth clauses of the no-op rule, with its `_deepen_to_the_cap` setup.
- `test_a_locked_milestone_refuses_the_change`: lock guards.
- `test_group_builds_the_parent_and_renumbers_in_argument_order`: A2.
- `test_group_keeps_the_parent_between_the_unlisted_siblings`: earliest-position rule.
- `test_group_at_the_root_stages_a_new_chunk_and_manifest_entry`: chunk and manifest in one plan.
- `test_a_refused_group_leaves_the_tree_byte_for_byte_unchanged`: A2 and A3 refusals.
- `test_a_group_that_fails_validation_rolls_everything_back`: A3 rollback.
- `test_grouping_ten_siblings_validates_the_roadmap_once`: A3.

Tests (`tests/test_gui_outline_contract.py`):
- `test_outline_group_returns_the_id_map`: A4 200 shape.
- `test_outline_group_refusals_are_400_with_a_string_detail`: A4 400 shape, malformed bodies included.
- `test_outline_group_under_a_locked_milestone_is_a_400_refusal`: A4 for a lock.
