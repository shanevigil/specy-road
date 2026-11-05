# Implementation summary: M21.4 `remove-node`

Branch `feature/rm-remove-node` (base `fcb4a96e29aef32add510850fe166939369f1473`).

## What changed, by acceptance item

- **A1:** Added `specy-road remove-node <ID> [--dry-run]`. One function, `remove_roadmap_node`, removes the chunk row and planning sheet in one transaction only when status is **Not Started** and there are no children, registry claims, or dependents. Otherwise it exits 1 with every blocker on stderr and writes nothing. `remove_node_blockers` collects status, claim (codename and branch), each child, and each dependent; `can_hard_remove` now delegates to that list.
- **A2:** `--dry-run` runs the same checks, prints the node id and planning-sheet path (or `(none)`), exits 0 when eligible and 1 when blocked, and leaves the tree byte-identical. Eligibility checks and refusals run before `heal_before_mutation`; only a committed removal heals first.
- **A3:** `DELETE /nodes/{id}` and `archive-node --hard-remove` still call `delete_roadmap_node_hard`, which is a thin alias for `remove_roadmap_node`. Response shapes are unchanged (200 `{ok, node_id}`; 400 `detail` is the joined blocker text). No GUI route edits were required.
- **A4:** `tests/test_remove_node.py` covers each blocker, combined blockers, dry-run (eligible and blocked), success with validate, refused removal without heal, archive `--hard-remove` on a claim, and GUI DELETE on a claim. `docs/roadmap-authoring.md` and `cli_usage.py` name `remove-node` as the supported path; `archive-node` remains documented as legacy hard-remove.

## Touch zones (final list)

Confirmed the brief's zones; none added or removed. `specy_road/gui_app_routes_nodes.py` was not edited because it already routed through `delete_roadmap_node_hard`.

- `specy_road/bundled_scripts/roadmap_crud_delete.py`
- `specy_road/bundled_scripts/roadmap_crud_argparse.py`
- `specy_road/bundled_scripts/roadmap_crud_ops.py` (re-exports only)
- `specy_road/cli.py`
- `specy_road/cli_usage.py`
- `docs/roadmap-authoring.md`
- `tests/test_remove_node.py` (new)

## Verification

- `python -m pytest tests/test_remove_node.py tests/test_gui_app*.py tests/test_roadmap_gui_*.py -q -n 4 -p no:cacheprovider`: 119 passed
- `python -m pytest tests/test_remove_node.py tests/test_roadmap_crud.py tests/test_roadmap_crud_atomicity.py tests/test_roadmap_crud_ops.py tests/test_cli.py -q -n 4 -p no:cacheprovider`: 75 passed
- `python -m ruff check specy_road/bundled_scripts/roadmap_crud_delete.py specy_road/bundled_scripts/roadmap_crud_argparse.py tests/test_remove_node.py`: clean
- `python -m specy_road.cli file-limits`: OK
- `specy-road validate`, `export --check`, `digest --check` on dogfood fixture: exit 0

## Added

### Helpers
- `roadmap_crud_delete.remove_node_blockers`: collects every eligibility refusal (A1).
- `roadmap_crud_delete.remove_roadmap_node`: shared remove/dry-run implementation (A1, A2).
- `roadmap_crud_delete._exit_on_value_error`: maps `ValueError` to CLI exit 1 (A1).
- `roadmap_crud_delete.cmd_remove_node`: `remove-node` CLI entry (A1).

### Branches and guards
- `remove_roadmap_node`: status, registry claim, children, and dependents checked before any heal or write (A1, A2).
- `remove_roadmap_node`: `dry_run` prints would-remove lines and returns without staging (A2).
- `can_hard_remove`: returns all blockers joined, not the first only (A1).
- `cmd_archive` `--hard-remove`: calls `remove_roadmap_node` instead of duplicating logic (A3).

### Mocks
- none

### Tests
- `tests/test_remove_node.py`: blocker matrix, combined blockers, dry-run byte identity, success + validate, no heal on refuse, archive claim refuse, GUI DELETE claim refuse (A4).
