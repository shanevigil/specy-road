# Implementation summary: M21.4 `remove-node`

Branch `feature/rm-remove-node` (base `fcb4a96e…`; fix rounds through `d59bd7d5`; fix round 3 `1569781e`; fix round 4 on top).

## What changed, by acceptance item

- **A1:** `remove-node` removes chunk row + planning sheet when eligible; refusals list all blockers; live repo unchanged on refuse.
- **A2:** `--dry-run` rehearses `_commit_remove` on `rehearsal_root` (scratch copy); live repo never written. Symlinks (file or directory) under the copied `roadmap/` and `planning/` that resolve into a live graph tree are **re-pointed** at the same path in the scratch copy by `_rebase_graph_symlinks`, so dry-run sees the layout real removal sees; other links are kept and resolve as they do live.
- **A3:** GUI routes unchanged; serial GUI + `test_gui_outline_contract.py` verified (135 passed).
- **A4:** Tests and docs as before; public `write_registry_claim`.

## Fix round 3 (`REVIEW-gpt-6.1-sol-low` on `d59bd7d5`)

| Finding | Class | Fix |
|--------|--------|-----|
| R1 | Scratch copy preserves absolute chunk symlinks pointing at live repo | `_materialize_graph_symlinks` after copytree; CLI test with `phases/T.json` → absolute symlink to in-repo storage. |
| R2 | GUI gate not completed (TestClient stall / timeout) | Re-ran full serial GUI suites in this environment: 135 passed (~13s). Stall class: intermittent blocking on first `TestClient.get` under reviewer timeout/contention, not remove-node code. |

## Fix round 4 (`REVIEW-gpt-6.1-sol-low` on `1569781e`)

| Finding | Class | Fix |
|--------|--------|-----|
| R1 | Symlinks in the scratch graph copy that resolve back into the live repo, any kind (file, directory, planning sheet) | Design change: replaced byte materialization (`_materialize_graph_symlinks`, files only, raised on directories and on out-of-repo links) with `_rebase_graph_symlinks` + `_scratch_target`: links into a live graph tree are re-pointed at the scratch copy (files and directories alike), all other links are left as-is so they resolve exactly as live. Parametrized CLI regression runs dry-run then real removal on each layout and asserts they agree and dry-run leaves the tree byte-identical. |
| R2 | GUI gate unverified (reviewer's run stalled at the first TestClient test) | No code change; re-ran the full serial GUI suites + unchanged `tests/test_gui_outline_contract.py` here: 135 passed in 12.2 s. Recorded in READY. |

## Touch zones (final list)

Brief zones; `tests/test_roadmap_crud.py` / `tests/test_generate_brief.py` for registry helper only.

## Verification (fix round 4)

- `tests/test_remove_node.py`: 18 passed
- Serial `tests/test_gui_app*.py tests/test_roadmap_gui_*.py tests/test_gui_outline_contract.py`: 135 passed
- Importers of changed modules + remove-node + brief tests (`-n 4`): 770 passed
- `ruff check specy_road tests scripts`, `file-limits`: OK
- Red-green: the `absolute-chunk-dir` and `planning-sheet-outside-graph` cases fail on `1569781e`'s `roadmap_crud_delete.py` (2 failed) and pass now.

## Verification (fix round 3)

- `tests/test_remove_node.py`: 16 passed
- Serial GUI + roadmap GUI + outline contract: 135 passed
- Non-GUI targeted review list (`-n 4`): run in READY
- `ruff check specy_road tests scripts`, `file-limits`: OK

## Probes

Fix round 4:
- **Absolute directory link `roadmap/phases -> <repo>/roadmap/storage` (reviewer's R1 layout):** dry-run exit 0, tree byte-identical; real removal exit 0, node gone. Failed on the previous code.
- **Absolute file link `roadmap/phases/T.json -> <repo>/roadmap/T-storage.json`:** dry-run and real both exit 0; dry-run tree unchanged.
- **Planning sheet linked to an in-repo file outside the graph trees (`planning/<sheet> -> <repo>/docs/<sheet>`):** real removal deletes the link target, then validation flags the dangling sheet and rolls back (exit 1, tree unchanged); dry-run now also exits 1 with tree unchanged. The previous code copied the bytes in and reported exit 0, so the two disagreed. Nothing is written live: the sheet resolves outside the scratch root, and `resolve_planning_path` refuses it before any staging.
- **Writes during rehearsal can reach live:** chunk writes go to `find_chunk_path`'s resolved path, which must sit under the scratch `roadmap/` (a real copy); sheet unlinks go to a path resolved under the scratch root. Rebased links resolve into scratch copies, so no write path reaches live.
- **`roadmap/` or `planning/` itself a symlink in live:** `_scratch_target` maps against each live top's *resolved* path, so links into the real location of a linked top are rebased too (traced, not tested).
- **Links leaving the repo, or dangling:** kept unchanged; they resolve the same as live, so lookup gives the same accept/reject (previously dry-run raised on them even when they were irrelevant to the node).
- **Directory links in walk:** `os.walk(followlinks=False)` doesn't descend into links, so rebasing can't loop and each copied file is visited once.
- **Other rehearsal callers:** `rehearsal_root` is used only by `remove_roadmap_node(dry_run=True)` (grep).
- **R2 (GUI gate):** serial 135-test GUI bundle incl. unchanged M21.1 outline contract: 135 passed in 12.2 s in this environment.

Fix round 3:

- **R1 class (graph symlinks in scratch rehearsal):** only `rehearsal_root` builds scratch trees for this leaf; `_materialize_graph_symlinks` runs for both `roadmap` and `planning` tops.
- **R1 instance (absolute chunk symlink):** `test_dry_run_succeeds_when_manifest_chunk_is_an_in_repo_symlink` — dry-run exit 0, live bytes and node id unchanged.
- **R1 relative in-repo symlinks:** materialize skips links already resolving under scratch anchor — unchanged relative links still work (existing dry-run tests).
- **R2 class (TestClient hang):** serial `test_gui_outline_contract.py` alone: 27 passed in ~4s here; full 135-test GUI bundle ~13s — no code change required.
- **R2 M21.1 contract:** `test_gui_outline_contract.py` included in serial GUI run, all passed.
- **Missing node id:** unchanged behaviour on dogfood-style probes.

## Added

### Helpers
- `roadmap_crud_delete._rebase_graph_symlinks`: re-points scratch graph-tree symlinks (file or dir) into the live graph trees at the scratch copy (R1, round 4; replaces round 3's `_materialize_graph_symlinks`, now removed).
- `roadmap_crud_delete._scratch_target`: maps a resolved live graph-tree path to its scratch counterpart (R1, round 4).
- `roadmap_crud_delete.rehearsal_root`, `_commit_remove`, `remove_node_blockers`, `remove_roadmap_node`, `cmd_remove_node`, etc. (prior rounds).

### Tests
- `test_dry_run_agrees_with_removal_on_in_repo_symlinks` (parametrized: absolute chunk file, absolute chunk directory, planning sheet outside the graph trees) with layout helpers `_link_chunk_file`, `_link_chunk_dir`, `_link_planning_sheet_outside_graph`: public CLI regression that dry-run and real removal agree and dry-run leaves the tree unchanged (R1; extends round 3's `test_dry_run_succeeds_when_manifest_chunk_is_an_in_repo_symlink`, which became its first case).

### Mocks
- none
