# Implementation summary: M22.4 — new planning sheets no longer write the node's display id into their body

Branch `feature/rm-sheet-body-without-display-id`. Fix round 1 after `faa4bf12`. Integration merges are on the branch; the product diff is the sheet change plus this round.

## What changed

- **A1.** Both sheet templates drop `{{NODE_ID}}` from the References line. It is now `Roadmap chunk: the node this sheet's file name names`. add-node, scaffold-planning, group-nodes and the PM GUI add all render that template through `render_planning_sheet_template`, so a new body does not contain the display id. The template rule against repeating the id or `node_key` in the body is unchanged.
- **Fix round (class: toolkit sheet text that copies this node's display id).** `promote_placeholder` no longer substitutes `node_id`. Brainstorm promote writes that return value under `## Approach`, so the sheet keeps the `<ID>` token. Pickup's skip reason still names the id; that line is not sheet text. Signature unchanged.
- **A2.** `group-nodes --into-new M1.9` then `move-node M1.9 --to-parent M1 --id M1.4` leaves a group sheet whose text names neither id. scaffold-planning for task `M99.1` and gate `M99.2` writes a body without the node id. The three bootstrap assertions are absence checks and still assert the placeholder is gone, plus the same path and section checks. The promote references assertion points at the new line. Promoted sheets assert the promoted id is absent. The other template tests are unchanged and pass.
- **A3.** `render_planning_sheet_template` still takes `node_id`. `_substitute_node_id` stays: a template with no placeholder renders unchanged, and both render functions still call it. `promote_placeholder` still takes `node_id` and does not write it. `CHANGELOG.md` `[Unreleased]` / `### Fixed` records the change. Existing sheets, the planning README and validators were not rewritten.

## Touch zones

`specy_road/templates/planning-node/feature-sheet.md.template`, `specy_road/templates/planning-node/gate-sheet.md.template`, `specy_road/bundled_scripts/planning_sheet_bootstrap.py`, `tests/test_planning_sheet_bootstrap.py`, `tests/test_outline_group_cli.py`, `tests/test_brainstorm_promote_judgement.py`, `CHANGELOG.md`, `tests/test_scaffold_planning.py`, `tests/test_author_approach.py`.

`brainstorm_promote.py` stays unchanged: it already writes `promote_placeholder(node["id"])`, and that function is the one substitution. No path outside these zones needed a change.

## Probes

- Feature and gate templates have no `{{NODE_ID}}`. Rendering `M9.9`, `M0.1` and a created `M1.1` sheet leaves those ids out. Result: the bootstrap absence tests pass.
- `promote_placeholder` was the remaining writer of this node's display id (`<ID>` became the id, then promote stored it under Approach). Result: it now returns `PROMOTE_PLACEHOLDER` unchanged; `promote_placeholder("M1")` does not contain `M1`.
- `seed_planning_sheet` on node `M1`. Result: the sheet text does not contain `M1`.
- `promote_session`, plain and with critics, overlaps and a verdict. Result: the sheet does not contain the promoted id. The judged References still name other nodes `M0.1` and `M0.2`.
- `_intent_body` writes the idea id (`i-1`), not the node display id. Result: covered by the whole-sheet absence checks.
- Overlap and "also promoted" lines name other nodes and idea ids. Result: covered by the judged-sheet check; the promoted id is absent.
- `placeholder_reason` and the plan's `author-approach` line name the id in skip and plan text, not in the sheet. Result: `test_pickup_skip_reason_names_the_same_command` and the unauthored-leaf tests still pass.
- `_substitute_node_id` still replaces `{{NODE_ID}}` when a template has that token. Current templates have none, so render emits no id. Result: no second sheet writer remains.
- The brainstorm authoring prompt file still names the node id. Result: left as-is; it is not the planning sheet.
- add-node, scaffold-planning, group-nodes and the PM GUI add all use `render_planning_sheet_template`. Result: the group-then-move test and the task and gate scaffold tests still show no id.

## Verification

- `pytest -n 4 tests/test_planning_sheet_bootstrap.py tests/test_outline_group_cli.py tests/test_brainstorm_promote_judgement.py tests/test_scaffold_planning.py tests/test_author_approach.py tests/test_unauthored_leaf_guard.py tests/test_brief_placeholder_intent.py tests/test_finish_scaffold_planning.py tests/test_one_readiness_rule.py`: 97 passed.
- `ruff check specy_road tests scripts`: all checks passed.
- `specy-road file-limits`: OK (existing hard-alert warnings only).

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
- Fix round: no new test. `test_placeholder_text_says_pickup_skips_and_names_the_command` and `test_promote_writes_the_placeholder_under_approach_not_intent` now require the placeholder and the seeded sheet to omit the display id. The two promote Approach tests require the same of the promoted sheet.
