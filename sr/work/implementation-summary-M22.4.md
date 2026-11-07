# Implementation summary: M22.4 — new planning sheets no longer write the node's display id into their body

Branch `feature/rm-sheet-body-without-display-id`, base `4877a3ba7de1ac62ab63c3b68b868884ad1940d5` (fast-forward onto `WIP/improvements-0-3-1` so the zone list includes `tests/test_scaffold_planning.py`).

## What changed

- **A1.** Both sheet templates drop `{{NODE_ID}}` from the References line. It is now `Roadmap chunk: the node this sheet's file name names`. add-node, scaffold-planning, group-nodes and the PM GUI add all render that template through `render_planning_sheet_template`, so a new body does not contain the display id. The template rule against repeating the id or `node_key` in the body is unchanged. Brainstorm promote still writes `promote_placeholder(node_id)` under `## Approach` (`specy-road author-approach <id>`); that string is a separate contract, and `tests/test_author_approach.py` (outside the zones) pins it. The References line promote leaves in place no longer carries the id.
- **A2.** `group-nodes --into-new M1.9` then `move-node M1.9 --to-parent M1 --id M1.4` leaves a group sheet whose text names neither id. scaffold-planning for task `M99.1` and gate `M99.2` writes a body without the node id. The three bootstrap assertions are absence checks and still assert the placeholder is gone, plus the same path and section checks. The promote references assertion points at the new line. The other template tests are unchanged and pass.
- **A3.** `render_planning_sheet_template` still takes `node_id`. `_substitute_node_id` stays: a template with no placeholder renders unchanged, and both render functions still call it. `CHANGELOG.md` `[Unreleased]` / `### Fixed` records the change. Existing sheets, the planning README and validators were not rewritten.

## Touch zones

Declared, after the WIP fast-forward: `specy_road/templates/planning-node/feature-sheet.md.template`, `specy_road/templates/planning-node/gate-sheet.md.template`, `specy_road/bundled_scripts/planning_sheet_bootstrap.py`, `tests/test_planning_sheet_bootstrap.py`, `tests/test_outline_group_cli.py`, `tests/test_brainstorm_promote_judgement.py`, `CHANGELOG.md`, `tests/test_scaffold_planning.py`.

`planning_sheet_bootstrap.py` stays unchanged: the public functions and signatures are the same, and nothing in that module writes the id except the placeholder substitution the templates no longer use. No path outside these zones needed a change.

## Verification

- `pytest -n 4 tests/test_planning_sheet_bootstrap.py tests/test_outline_group_cli.py tests/test_brainstorm_promote_judgement.py tests/test_scaffold_planning.py tests/test_author_approach.py tests/test_unauthored_leaf_guard.py tests/test_brief_placeholder_intent.py tests/test_finish_scaffold_planning.py tests/test_one_readiness_rule.py`: 97 passed.

## Added

### Helpers

- none

### Branches or guards

- none

### Mocks

- none

### Tests

- `test_a_renamed_group_sheet_names_neither_temporary_nor_final_id` — group-nodes into `M1.9` then move-node to `M1.4` leaves a group sheet that names neither id (A2).
- `test_scaffold_restores_a_missing_gate_sheet_without_the_node_id` — scaffold-planning a gate writes the gate template with no display id in the body (A2). The task case is the existing test, flipped to absence.
