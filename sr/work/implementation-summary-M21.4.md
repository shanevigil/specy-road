# Implementation summary: M21.4 `remove-node`

Branch `feature/rm-remove-node` (base `fcb4a96e29aef32add510850fe166939369f1473`; round 0 `b4d9efa6`; fix round 1 `95c60c81`; fix round 2 after merge with `origin/WIP/improvements-0-3-1`).

## What changed, by acceptance item

- **A1:** `specy-road remove-node <ID> [--dry-run]` removes the chunk row and planning sheet only when status is **Not Started** and there are no children, registry claims, or dependents; refusals list every blocker and write nothing on the live repo.
- **A2:** `--dry-run` checks eligibility on the live graph, then rehearses the same `AtomicWritePlan.commit` + `validate_callback` on a **scratch copy** (`rehearsal_root`); the live tree is never written or unlinked. Success prints the node id and planning-sheet path; exit 0 when rehearsal succeeds, 1 otherwise.
- **A3:** `DELETE /nodes/{id}` and `archive-node --hard-remove` use `delete_roadmap_node_hard` → `remove_roadmap_node`. GUI API suites and `tests/test_gui_outline_contract.py` (M21.1 contract) pass when run serially (see fix round 2).
- **A4:** `tests/test_remove_node.py` plus docs/cli_usage; public `write_registry_claim` fixture helper.

## Fix round 2 (`REVIEW-gpt-6.1-sol-low` on `95c60c81`)

| Finding | Class | Fix |
|--------|--------|-----|
| R1 | Dry-run mutates the live tree (write then rollback) | `--dry-run` uses `rehearsal_root` + `_commit_remove` on scratch only; live repo untouched. |
| R2 | GUI / M21.1 contract gate not completed (TestClient stall under `-n 4`) | Re-ran GUI + outline contract tests **without** xdist; 135 passed in ~13s. Stall class: parallel workers + shared TestClient lifecycle, not remove-node code. |

## Touch zones (final list)

Brief zones plus `tests/test_roadmap_crud.py` / `tests/test_generate_brief.py` (registry helper rename only).

## Verification (fix round 2)

- Non-GUI targeted suite (review list, `-n 4`): 306 passed
- GUI + roadmap GUI + `test_gui_outline_contract.py` (serial, `-p no:cacheprovider`): 135 passed
- `python -m ruff check specy_road tests scripts`: clean
- `python -m specy_road.cli file-limits`: OK

## Probes

- **R1 class (live-repo dry-run mutation):** `remove_roadmap_node(..., dry_run=True)` only writes via `_commit_remove` inside `rehearsal_root`; real removal uses `_commit_remove` on live root — no other dry-run paths in this leaf.
- **R1 instance (write/rollback on live):** eligible `--dry-run` leaves node `M99.2` in `load_roadmap` and `_tree_bytes` unchanged; invalid post-graph fixture still exit 1 with unchanged live bytes (parametrized real + dry-run).
- **R1 public API:** CLI `--dry-run` subprocess tests above; `rehearsal_root` exported from `roadmap_crud_ops` for reuse/tests.
- **R2 class (GUI gate under parallel pytest):** `pytest -n 4` on `test_gui_outline_contract.py` reproduced reviewer interrupt (environment); same files pass serially — documented limit: run GUI PM tests without xdist on shared machines.
- **R2 instance (M21.1 contract):** full `tests/test_gui_outline_contract.py` serial run: 27 passed (includes delete shape and outline move cases).
- **Missing node id:** unchanged — blockers `[]`, remove APIs raise or exit 1 as before.

## Added

### Helpers
- `roadmap_crud_delete.remove_node_blockers`, `remove_roadmap_node`, `_commit_remove`, `rehearsal_root`, `_exit_on_value_error`, `cmd_remove_node`.
- `tests/test_roadmap_crud.write_registry_claim`.

### Branches and guards
- `_commit_remove`: single commit path for live removal and scratch rehearsal.
- `remove_roadmap_node`: dry-run → scratch rehearsal only; else `_commit_remove` on live root.

### Mocks
- none

### Tests
- `tests/test_remove_node.py`: blockers, dry-run live graph preserved, validation refusal bytes, archive/GUI claim refuse.
