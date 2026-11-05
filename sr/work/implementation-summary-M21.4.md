# Implementation summary: M21.4 `remove-node`

Branch `feature/rm-remove-node` (base `fcb4a96e29aef32add510850fe166939369f1473`; round 0 `b4d9efa6`; fix round 1 after merge with `origin/WIP/improvements-0-3-1`).

## What changed, by acceptance item

- **A1:** Added `specy-road remove-node <ID> [--dry-run]`. One function, `remove_roadmap_node`, removes the chunk row and planning sheet only when status is **Not Started** and there are no children, registry claims, or dependents. Otherwise it exits 1 with every blocker on stderr and writes nothing. Refused removals never call `heal_before_mutation`; side effects go only through `AtomicWritePlan`, which rolls back on validation failure.
- **A2:** `--dry-run` runs the same eligibility checks and the same post-delete `validate_callback` path as real removal (write → validate → rollback), then prints the node id and planning-sheet path when validation succeeds; exit 0 when eligible, 1 when blocked or when the resulting graph fails validation; no persistent bytes.
- **A3:** `DELETE /nodes/{id}` and `archive-node --hard-remove` still call `delete_roadmap_node_hard` → `remove_roadmap_node`. Response shapes unchanged.
- **A4:** `tests/test_remove_node.py` covers blockers, dry-run, validation-refused byte identity (real and dry-run), healable-graph probe, archive claim, GUI DELETE claim. `write_registry_claim` in `tests/test_roadmap_crud.py` is the public fixture helper (no `_`-prefixed imports). Docs name `remove-node` as the supported path.

## Fix round 1 (`REVIEW-gpt-6.1-sol-low` on `b4d9efa6`)

| Finding | Class | Fix |
|--------|--------|-----|
| R1 | Side-effect writes outside the atomic transaction (self-heal before commit) | Dropped `heal_before_mutation` from the remove path; all persistence goes through `AtomicWritePlan.commit` or dry-run write/validate/rollback. |
| R2 | Dry-run skipping resulting-graph validation | Dry-run uses the same staged delete + `validate_callback` as commit, always rolling back afterward. |
| R3 | Test importing a private `_`-prefixed helper | Renamed to `write_registry_claim` in `tests/test_roadmap_crud.py`; callers updated. |

## Touch zones (final list)

Unchanged from round 0; `tests/test_roadmap_crud.py` and `tests/test_generate_brief.py` touched only for the public registry helper rename.

## Verification (fix round 1)

- `PYTHONDONTWRITEBYTECODE=1 python -m pytest tests/test_remove_node.py tests/test_roadmap_crud*.py tests/test_cli.py tests/test_registry_overlap_warnings.py tests/test_validate_stale_commands.py tests/test_behaviour_changes.py tests/test_planned_test_changes.py tests/test_roadmap_edit_fields.py tests/test_milestone_review_hold_notice.py tests/test_ready_command.py tests/test_worker_reconcile_contract.py -k 'not gui' -q -n 4 -p no:cacheprovider`: 207 passed
- `python -m ruff check specy_road tests scripts`: clean
- `python -m specy_road.cli file-limits`: OK

## Probes

- **R1 class (pre-transaction side effects):** `remove_roadmap_node` and `delete_roadmap_node_hard` only — no other call sites invoke `heal_before_mutation` on this path after the fix; refused removal with healable chunk bytes (`parallel_tracks=0`, missing codename) leaves `_tree_bytes` unchanged (parametrized real + dry-run).
- **R1 instance (validation refusal):** `M99.1 type='invalid'`, remove `M99.2` real — exit 1, full tree bytes unchanged.
- **R2 class (dry-run vs commit validation):** same invalid-graph fixture — dry-run also exit 1 with unchanged bytes; eligible dry-run still exit 0 with unchanged bytes (existing test).
- **R2 instance (review probe):** independent re-run of invalid-type fixture matches review (dry-run no longer returns 0 when real removal would fail validation).
- **R3 class (`_`-prefixed test imports):** grep for `_write_registry_claim` — none remain; `write_registry_claim` used from `test_remove_node.py` and `test_generate_brief.py`.
- **Unknown node id:** `remove_node_blockers` still returns `[]` for missing ids; locate/remove still raises via `unknown_node_msg` (unchanged public behaviour).

## Added

### Helpers
- `roadmap_crud_delete.remove_node_blockers`: collects every eligibility refusal (A1).
- `roadmap_crud_delete.remove_roadmap_node`: shared remove/dry-run implementation with atomic validate (A1, A2).
- `roadmap_crud_delete._exit_on_value_error`: maps `ValueError` to CLI exit 1 (A1).
- `roadmap_crud_delete.cmd_remove_node`: `remove-node` CLI entry (A1).
- `tests/test_roadmap_crud.write_registry_claim`: public registry fixture helper (R3).

### Branches and guards
- `remove_roadmap_node`: eligibility before any write; real path `plan.commit(validate)`; dry-run `write` → `validate` → `rollback` then print (A1, A2).
- `can_hard_remove`: all blockers joined (A1).
- `cmd_archive` `--hard-remove`: calls `remove_roadmap_node` (A3).

### Mocks
- none

### Tests
- `tests/test_remove_node.py`: blocker matrix, combined blockers, dry-run byte identity, post-graph validation refusal (real + dry-run), healable-bytes refusal (real + dry-run), blocker tree preservation, archive/GUI claim refuse (A4, R1–R3).
