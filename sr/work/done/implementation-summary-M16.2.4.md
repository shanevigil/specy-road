# Implementation summary — M16.2.4

One roadmap index answers every graph query: by id, by key, effective dependencies, unmet, ready.

## What changed

- **New `specy_road/bundled_scripts/roadmap_index.py`**: `RoadmapIndex(nodes, *, status_overrides=None, claimed=())` with lazily computed `by_id`, `by_key`, `status` (lowercased rollup per node_key, overrides applied before the rollup — the former `_statuses_by_node_key` body), `effective_dependencies` (the former `roadmap_layout.effective_dependency_keys` body), `leaf_ids`, `outline_position`, `unmet(node, statuses=None)` (sorted unmet effective dependency keys; `statuses` keeps the interactive picker's "integration statuses only" question) and `ready()` (pickable unclaimed leaves with a codename, not Complete/Cancelled, deps met, in outline order).
- **do_next_available**: `_available` takes its base set from `index.ready()` and keeps its tiers; `_leaf_diagnostics` and `interactive_deps_blocked_entries` call `index.unmet`; `_statuses_by_node_key` returns `RoadmapIndex(...).status` (kept: do_next_task and tests import it). Removed `_unmet_effective_dependency_keys`, `_effective_deps_met`, `_base_agentic_candidate`, `_outline_order_index`.
- **session_plan**: `_classify`, `_open_gates_blocking` and `_compute_waves` read one index from ctx; removed `_unmet_dep_keys`, `_gate_keys` and the four key/id maps.
- **roadmap_explain**: `_walk`, `explain`, `open_gates` use the index; removed `_by_id`, `_unmet`, `_context`.
- **roadmap_layout**: `effective_dependency_keys` returns the index's map (name kept for its ~20 callers); `compute_dependency_steps`, `dependency_edges_detailed`, `dependency_inheritance_display` use `index.by_key`/`by_id`.
- **brief_dependency_context.effective_dep_nodes** and **digest** (`_key_to_node` removed) use the index.
- `roadmap_load.py` needed no change (the index calls its `compute_rollup_status`). Final zones: as listed, `roadmap_load.py` unchanged.

Import direction: `roadmap_layout` and `digest` import `RoadmapIndex` at top level; the index imports `ordered_tree_rows` inside `outline_position` (one commented function-level import, ruff PLC0415 +1 in the new file), because layout's dependency maps now come from the index.

## Parity

- Full suite `pytest -n 4`: 7170 passed, 18 skipped. Do-next, session-plan, why-blocked (`test_roadmap_explain`), brief, digest and parity tests are unchanged and green, including the feature-tip-Complete pickup cases in `tests/test_do_next_virtual_pickup.py`.
- Dogfood `validate`, `export --check`, `digest --check` OK; `sr/` `digest --check` OK (digest output unchanged).
- Old-vs-new probe (base commit's package vs this branch) over the `sr/` roadmap and the dogfood graph: `_available` (plain, and with overrides + virtual keys + prefer_agentic), `_leaf_diagnostics`, `interactive_deps_blocked_entries`, `compute_session_plan`, `explain` for every node, `open_gates`, the three layout maps, `compute_dependency_steps` and `effective_dep_nodes` for every node — identical. The only byte difference was the order of `dependency_edges_detailed`, which iterates a set of string keys and already varies with `PYTHONHASHSEED` on the base commit; as sorted sets they are equal.
- Red-green for A3: adding `X = {n["id"]: n for n in []}` in a scratch module under `specy_road/` made `test_graph_lookups_outside_the_index_only_shrink` fail (69 > 68); removed afterwards.

## Metrics

- Hand-built lookup count (A3 patterns): 84 at base, 68 now; baseline committed as 68.
- Lines over 100: no file above its baseline; session_plan 4 → 3.
- Ruff families on touched files: do_next_available SIM 1 → 0; roadmap_index PL 1 (the function-level import above); others at baseline. No function's C901 rose (do_next_available keeps its one existing waived `_collect_do_next_tiers`, unchanged).
- `ruff check specy_road tests scripts`, `specy-road file-limits`, `check_test_private_imports` (0 new; `test_archive_dependencies`' two do_next private entries are now stale), `check_clones` (0 new): pass.
- `scripts/lean_metrics.py --check` did not finish within the 10-minute tool limit, so no lean_metrics delta is reported here. Package lines from git: +247 −291 including the new 149-line module, net about −44 (A5 estimated about −250; informational).

## Added

- `RoadmapIndex` (roadmap_index.py): the single index the acceptance requires.
- `CLOSED_STATUSES` constant: the own statuses `ready()` excludes (every pickup tier already skipped them).
- `unmet(..., statuses=)` parameter: keeps `interactive_deps_blocked_entries`' existing `integration_statuses` argument meaningful without a second index.
- Function-level import of `ordered_tree_rows` in `outline_position`: breaks the import cycle with roadmap_layout.
- `tests/test_roadmap_index.py::test_roadmap_index_answers` (15 table rows): A1, covering inherited dependencies, a gate dependency, milestones, stable keys, overrides and outline order.
- `tests/test_graph_lookup_count.py::test_graph_lookups_outside_the_index_only_shrink`: A3 shrink-only count with a committed baseline.
- `tests/test_graph_lookup_count.py::test_counter_matches_each_pattern` (7 rows): proves the counter matches each pattern and ignores near misses, so the count cannot silently match nothing.
- Changed `tests/test_archive_dependencies.py::_leaf_is_dep_blocked` to `RoadmapIndex.unmet`, because `_unmet_effective_dependency_keys` was removed (same assertions).
- Mocks: none.
