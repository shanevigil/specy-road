# Implementation summary: M11.18 — quieter overlap warnings

## Goal

Registry overlap warnings during add-node and edit-node should mention only claims that clash with the node being authored. Full `validate` should still report every clash, but collapse broad shared directory zones (for example `tests/`) into one summary line and keep non-broad claim pairs at one line each.

## Touch zones (confirmed)

- `specy_road/bundled_scripts/validate_roadmap.py` — passes authoring overlap scope into validation
- `specy_road/bundled_scripts/validate_roadmap_checks.py` — wires overlap reporting into `run_validation`
- `specy_road/bundled_scripts/validate_registry_overlap.py` — overlap logic and authoring scope
- `specy_road/bundled_scripts/roadmap_crud_ops.py` — wraps chunk writes in authoring overlap scope
- `tests/test_registry_overlap_warnings.py` — behavioural coverage

## Acceptance

- **A1:** Authoring scope carries `node_id`; scoped reporting skips the authored node's own registry claim. `cmd_edit` on a sole claim with `touch_zones=tests/` emits no self-overlap warning.
- **A2:** Pair lines skip clashes already represented by a shared-zone summary (including directory vs nested paths under that directory). Independent collisions on the same specific file path still emit one pair line.

## Review fixes (Codex Sol)

- **R1:** `AuthoringOverlapScope` includes `node_id`; scoped loop skips `entry.node_id == scope_node_id`. `test_touch_zone_overlap_scoped_skips_the_authored_nodes_own_claim` and `test_edit_node_cli_does_not_warn_self_overlap_on_claim` cover reporter and public `edit-node`.
- **R2:** `_clash_suppressed_by_broad_summary` / `_first_independent_pair_clash` drop broad-tree pair spam after summaries. `test_touch_zone_overlap_validate_skips_nested_clashes_under_summarized_broad` and `test_touch_zone_overlap_keeps_same_specific_file_under_shared_directory` cover nested-only vs same-file collisions.

## Verification

- `pytest tests/test_registry_overlap_warnings.py tests/test_validate_roadmap.py tests/test_roadmap_crud_ops.py`
- `specy-road file-limits`

## Added

- `AuthoringOverlapScope` NamedTuple — label, node_id, and touch_zones for scoped validation (R1)
- `_clash_suppressed_by_broad_summary` / `_first_independent_pair_clash` — suppress pair lines covered by shared-directory summaries (R2)
- `test_touch_zone_overlap_scoped_skips_the_authored_nodes_own_claim` — R1 scoped self-claim exclusion
- `test_edit_node_cli_does_not_warn_self_overlap_on_claim` — R1 through public edit-node CLI
- `test_touch_zone_overlap_validate_skips_nested_clashes_under_summarized_broad` — R2 nested paths under summarized `tests/`
- `test_touch_zone_overlap_keeps_same_specific_file_under_shared_directory` — R2 retains identical specific-file pair line
