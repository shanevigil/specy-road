# Implementation summary — M11.48 (claimed-leaf-status)

## Summary

`list-nodes` and `specy-road brief` now surface an active registry claim for structural leaves: table status `… (claimed)`, JSON `claimed`/`branch`, and brief **Status (own)** with branch and owner. `docs/pm-workflow.md` adds a short walkthrough of pickup → finish → PR merge under `on_complete: pr`, separating chunk `status` from the integration-branch registry row.

## Changes

- **`roadmap_crud_ops.cmd_list`** — loads `registry.yaml`, resolves leaf claims, annotates text and `--json` output (imports shared helpers from `generate_brief.py`).
- **`generate_brief`** — shared claim helpers (`leaf_claim_entry`, `list_nodes_*`, `brief_status_own_line`); `render_brief` reads the registry and passes claim into metadata.
- **Tests** — claimed vs unclaimed `list-nodes`; brief claim line next to status.
- **`docs/pm-workflow.md`** — new section on status vs claim and the four-step `pr` lifecycle.

## Touch zones (confirmed)

`specy_road/bundled_scripts/roadmap_crud_ops.py`, `specy_road/bundled_scripts/generate_brief.py`, `tests/`, `docs/pm-workflow.md` — no additions; claim helpers live in `generate_brief.py` to stay within file line limits.

## Verification

- `pytest tests/test_roadmap_crud.py tests/test_generate_brief.py`
- `specy-road file-limits`

## Added

- `leaf_claim_entry` in `generate_brief.py` — resolve a structural leaf’s active registry row by `node_id`.
- `list_nodes_status_label` in `generate_brief.py` — format table STATUS as `{status} (claimed)` when claimed.
- `list_nodes_json_row` in `generate_brief.py` — add `claimed` and optional `branch` to `--json` rows.
- `brief_status_own_line` in `generate_brief.py` — append branch and owner to brief **Status (own)**.
- Registry load in `cmd_list` — read claim index once per invocation for list output.
- Registry load in `render_brief` — same claim resolution for the brief metadata section.
- `test_list_nodes_marks_a_claimed_leaf_in_the_table_and_json` — A1 table + JSON for claimed and unclaimed leaves.
- `_write_registry_claim` in `test_roadmap_crud.py` — minimal registry fixture for list-nodes tests.
- `test_render_brief_shows_registry_claim_next_to_status` — A2 brief line with branch and owner.
- `claimed: false` assertion in `test_list_nodes_json_is_the_full_untruncated_list` — unclaimed JSON shape.
- pm-workflow section **Node status vs registry claim** — A3 step-through under `on_complete: pr`.
