# Implementation summary: M11.18 — quieter overlap warnings

## Goal

Registry overlap warnings during add-node and edit-node should mention only claims that clash with the node being authored. Full `validate` should still report every clash, but collapse broad shared directory zones (for example `tests/`) into one summary line and keep non-broad claim pairs at one line each.

## Touch zones (confirmed)

- `specy_road/bundled_scripts/validate_roadmap.py` — passes authoring overlap scope into validation
- `specy_road/bundled_scripts/validate_roadmap_checks.py` — wires overlap reporting into `run_validation`
- `specy_road/bundled_scripts/validate_registry_overlap.py` — overlap logic and authoring scope (added; required for file limits and cohesion)
- `specy_road/bundled_scripts/roadmap_crud_ops.py` — wraps chunk writes in authoring overlap scope
- `tests/test_registry_overlap_warnings.py` — behavioural coverage (added)
- `tests/test_validate_roadmap.py` — removed duplicate overlap import/test relocation only

## Acceptance

- **A1:** `authoring_overlap_for_node` / `authoring_overlap_scope` set a contextvar read by `validate_at` → `run_validation` → scoped `touch_zone_overlap`. Add-node and edit-node post-write validation runs inside that scope. Unscoped validate uses the full reporter.
- **A2:** `touch_zone_overlap` without scope emits one shared-zone summary per broad directory zone listed by two or more claims, skips redundant `tests/' vs 'tests/'` pair lines, and still emits one line per claim pair for specific path clashes.

## Verification

- `pytest tests/test_registry_overlap_warnings.py tests/test_validate_roadmap.py tests/test_roadmap_crud_ops.py`
- `specy-road file-limits`

## Added

- `specy_road/bundled_scripts/validate_registry_overlap.py` — overlap clash helpers, scoped/full reporting, authoring contextvar, `warn_registry_touch_zone_overlap` entry for validate
- `authoring_overlap_for_node` — context manager for add-node/edit-node without duplicating label/zone extraction in CRUD
- `_validate_registry_entries` in `validate_roadmap_checks.py` — keeps `run_validation` under the per-function line cap after overlap wiring
- `tests/test_registry_overlap_warnings.py::test_touch_zone_overlap_scoped_skips_unrelated_claim_pairs` — A1 scoped filtering
- `tests/test_registry_overlap_warnings.py::test_touch_zone_overlap_validate_summarizes_broad_shared_zone` — A2 broad zone summary
- `tests/test_registry_overlap_warnings.py::test_touch_zone_overlap_validate_one_line_per_specific_pair` — A2 pair line for specific paths alongside broad summary
- `tests/test_registry_overlap_warnings.py::test_touch_zone_overlap_warns_on_same_path` — regression for simple same-path overlap
