# Implementation summary: M11.17 (`edit-node-names-chunks`)

## Goal

`edit-node` and `add-node` now print where the node was read from (edits), every roadmap file the mutation wrote, an explicit **moved from … to …** line when overflow relocation runs, and a one-line `commit these files:` list (including `roadmap/manifest.json` when the router creates a chunk).

## Touch zones (confirmed)

PM listed `roadmap_crud_ops.py`, `roadmap_crud_argparse.py`, and `tests/`. `roadmap_crud_argparse.py` needed no edits. Added `specy_road/bundled_scripts/roadmap_crud_chunk_report.py` so `roadmap_crud_ops.py` stays under the 400-line cap.

## Behaviour

- **`edit-node`:** `edit_node_set_pairs` plans touched paths with the same overflow/relocation rules as `roadmap_chunk_router.write_node_update`, performs the write, then `cmd_edit` prints provenance via `print_node_chunk_write_report`.
- **`add-node`:** After dependency resolution and codename planning, `plan_add_chunk_writes` lists the target chunk, scaffolded planning sheet, and manifest when a new chunk is created; `cmd_add` prints the same report format.
- **In-place edit:** `read from` + `wrote` name the same chunk; commit list is that chunk only.
- **Relocation:** `read from` source chunk, `moved from` source `to` destination, commit list includes source, destination, and manifest when applicable.

## Verification

- `specy-road file-limits`
- `pytest tests/test_roadmap_crud_edit_node_chunks.py`
- `pytest tests/test_roadmap_crud.py tests/test_roadmap_crud_atomicity.py tests/test_roadmap_crud_edit_add_remove.py tests/test_roadmap_crud_edit_claim_zones.py`

## Added

- `roadmap_crud_chunk_report.py` — `NodeChunkWriteReport`, `plan_edit_chunk_writes`, `plan_add_chunk_writes`, `print_node_chunk_write_report`, `repo_rel`; mirrors router relocation planning for accurate commit lists without changing `roadmap_chunk_router.py`.
- `plan_edit_chunk_writes` — predicts source/dest/manifest paths before `write_node_update` runs.
- `plan_add_chunk_writes` — predicts chunk, planning sheet, and manifest for `add-node`.
- `print_node_chunk_write_report` — stdout format for A1 (`read from`, `moved from`, `wrote`, `commit these files`).
- `edit_node_set_pairs` return value — `NodeChunkWriteReport` for callers; assert holding chunk appears in planned paths.
- `tests/test_roadmap_crud_edit_node_chunks.py` — in-place edit, relocation, add-node in chunk, add-node with new chunk (A2).
