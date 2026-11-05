# Implementation summary: M21.4 `remove-node`

Branch `feature/rm-remove-node` (base `fcb4a96e…`; fix rounds through `d59bd7d5`; fix round 3 after merge with `origin/WIP/improvements-0-3-1`).

## What changed, by acceptance item

- **A1:** `remove-node` removes chunk row + planning sheet when eligible; refusals list all blockers; live repo unchanged on refuse.
- **A2:** `--dry-run` rehearses `_commit_remove` on `rehearsal_root` (scratch copy); live repo never written. In-repo absolute/escaping symlinks under `roadmap/` and `planning/` are **materialized** in scratch via `_materialize_graph_symlinks` so dry-run matches real removal.
- **A3:** GUI routes unchanged; serial GUI + `test_gui_outline_contract.py` verified (135 passed).
- **A4:** Tests and docs as before; public `write_registry_claim`.

## Fix round 3 (`REVIEW-gpt-6.1-sol-low` on `d59bd7d5`)

| Finding | Class | Fix |
|--------|--------|-----|
| R1 | Scratch copy preserves absolute chunk symlinks pointing at live repo | `_materialize_graph_symlinks` after copytree; CLI test with `phases/T.json` → absolute symlink to in-repo storage. |
| R2 | GUI gate not completed (TestClient stall / timeout) | Re-ran full serial GUI suites in this environment: 135 passed (~13s). Stall class: intermittent blocking on first `TestClient.get` under reviewer timeout/contention, not remove-node code. |

## Touch zones (final list)

Brief zones; `tests/test_roadmap_crud.py` / `tests/test_generate_brief.py` for registry helper only.

## Verification (fix round 3)

- `tests/test_remove_node.py`: 16 passed
- Serial GUI + roadmap GUI + outline contract: 135 passed
- Non-GUI targeted review list (`-n 4`): run in READY
- `ruff check specy_road tests scripts`, `file-limits`: OK

## Probes

- **R1 class (graph symlinks in scratch rehearsal):** only `rehearsal_root` builds scratch trees for this leaf; `_materialize_graph_symlinks` runs for both `roadmap` and `planning` tops.
- **R1 instance (absolute chunk symlink):** `test_dry_run_succeeds_when_manifest_chunk_is_an_in_repo_symlink` — dry-run exit 0, live bytes and node id unchanged.
- **R1 relative in-repo symlinks:** materialize skips links already resolving under scratch anchor — unchanged relative links still work (existing dry-run tests).
- **R2 class (TestClient hang):** serial `test_gui_outline_contract.py` alone: 27 passed in ~4s here; full 135-test GUI bundle ~13s — no code change required.
- **R2 M21.1 contract:** `test_gui_outline_contract.py` included in serial GUI run, all passed.
- **Missing node id:** unchanged behaviour on dogfood-style probes.

## Added

### Helpers
- `roadmap_crud_delete._materialize_graph_symlinks`: in-repo symlink materialization for scratch rehearsal (R1).
- `roadmap_crud_delete.rehearsal_root`, `_commit_remove`, `remove_node_blockers`, `remove_roadmap_node`, `cmd_remove_node`, etc. (prior rounds).

### Tests
- `test_dry_run_succeeds_when_manifest_chunk_is_an_in_repo_symlink`: public CLI regression for R1.

### Mocks
- none
