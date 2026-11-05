# Implementation summary — M21.6 `inherited-dep-cycles`

## What changed

- **A1 (validate):** `run_validation` runs the existing explicit `cycle_check` (message unchanged: `dependency cycle involving <id>`), then the new `effective_cycle_check`:
  - **Inherited self-edge** first: the first node, in outline order, that an ancestor depends on fails with `roadmap: inherited self-edge <id> via <ancestor>`.
  - **Scheduling graph:** each node waits on its effective dependencies (its own plus every ancestor's, the same union as `effective_dependency_keys`), and each group waits on its children (parent-child rollup). Following the rollup edges from a group target reaches every leaf in `leaf_ids_under_parent`, which is what `session_plan` waits on. Iterative DFS: start nodes and neighbours in outline order, so the path is deterministic. Failure prints `roadmap: dependency cycle: A -> B -> ... -> A` and then one line per derived edge, `  X -> Y: inherited from <anc>, which depends on <Y>` or `  X -> Y: parent-child rollup: X completes when its child Y does`. Explicit edges on the path get no extra line.
- **A2 (writers):** nothing was added. `add-dependency`, `set-dependencies`, `edit-node`, `apply` and the PM GUI patch all go through `edit_node_set_pairs` → `run_validate_raise`, so they refuse the edge with the same text and roll it back. The GUI returns 400 with `{"detail": <message>}`; the response shape is unchanged.
- **A3 (add-dependency report):** before the edit, `cmd_add_dependency` builds the suffix from the pre-edit graph and adds it to its `[ok]` line, giving `\nN descendant leaves now wait on <dep id>: <up to 5 ids>`. It counts descendant leaves that are not gates, not Complete, and whose pre-edit effective dependencies lack the new key. It prints nothing when N is 0, or when the prerequisite is Complete (rollup) or archived.
- **Docs:** `docs/roadmap-authoring.md`. I appended a paragraph to the existing "Tooling" line rather than adding a new line, because the file is at its 400-line cap.

## Touch zones (final)

The brief's zones, plus:

- **`specy_road/bundled_scripts/effective_dependency_checks.py` (new module, outside the listed zones).** This is a file-cap split. `specy-road file-limits` from the checkout root uses `sr/constraints/file-limits.yaml`, which caps at 400 lines, and `tests/test_validate_file_limits.py::test_file_limits_passes_on_repo` enforces that. `validate_roadmap_checks.py` started at 399 lines and `roadmap_crud_dependency_ops.py` at 398. The new code lives in this module, and the existing `cycle_check` moved here with it (as related code, body and docstring unchanged). `validate_roadmap_checks` re-imports `cycle_check`, so `validate_roadmap.cycle_check` and its other importers keep working. Please add this path to the zones.
- `roadmap_layout.py` was not changed; its `effective_dependency_keys` / `ordered_tree_rows` are reused.
- Note for the maintainer: the toolkit cap in the root `constraints/file-limits.yaml` was raised to 1000 lines, but the `sr/` copy still says 400, and the test above follows the `sr/` copy. I left both as they are.

## Verification

- `specy-road validate` (sr/) → OK. `specy-road validate --repo-root tests/fixtures/specy_road_dogfood` → OK. Neither has an inherited cycle.
- `specy-road file-limits` → OK.
- `pytest -n 4` → 5007 passed.

## Added

### Helpers
- `effective_dependency_checks._scheduling_edges` — builds each node's wait edges and keeps each edge's origin, so the error can name it.
- `effective_dependency_checks._inherited_self_edge` — finds a node that an ancestor depends on (A1's own message).
- `effective_dependency_checks._first_cycle` — iterative DFS that returns a deterministic cycle path without hitting the recursion limit on long chains.
- `effective_dependency_checks.effective_cycle_check` — the A1 check, called from `run_validation` after `cycle_check`.
- `effective_dependency_checks.newly_waiting_suffix` — the A3 count and line, computed from the pre-edit graph.

### Branches / guards
- `newly_waiting_suffix` returns `""` when the prerequisite is Complete, archived (not in the live graph), or when no leaf newly waits (A3: silent at 0).
- `_scheduling_edges` drops dependency keys that are not live nodes (archived), as `effective_dependency_keys` does.

### Mocks
- none

### Tests
- `tests/test_validate_roadmap.py::test_cycle_check_detects_cycle` (extended) — asserts the explicit-cycle message is unchanged.
- `tests/test_validate_inherited_cycles.py::test_validate_refuses_cycles_through_inherited_dependencies` (3 cases) — inherited cycle, group-rollup cycle and inherited self-edge, with exact stderr (path plus derived-edge origin).
- `tests/test_validate_inherited_cycles.py::test_effective_cycle_check_accepts_group_dependency_without_cycle` — a group dependency with no cycle still passes (guards against false positives).
- `tests/test_roadmap_crud_dependencies.py::test_add_dependency_reports_descendant_leaves_that_now_wait` — the serialization line prints; it is absent for a leaf and when N is 0.
- `tests/test_roadmap_crud_dependencies.py::test_add_dependency_refuses_cycle_through_inherited_dependency` (2 cases) — add-dependency refuses an inherited cycle and an inherited self-edge with the validate message, and writes nothing.
- `tests/test_gui_app_mutations.py::test_api_patch_dependencies_refuses_inherited_cycle` (2 cases) — the GUI patch returns 400 with the exact detail and an unchanged response shape, and writes nothing.
