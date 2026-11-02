# Implementation summary: M11.17 (`edit-node-names-chunks`)

## Goal

`edit-node` and `add-node` print where the node was read from (edits), every roadmap file the mutation wrote, an explicit **moved from … to …** line when overflow relocation runs, and a one-line `commit these files:` list. That list includes the manifest on a new chunk, both sides of a planning-sheet rename, `roadmap/registry.yaml` when a claim's `touch_zones` actually change, and every file the pre-mutation heal rewrote (including a heal in another chunk).

## Touch zones (confirmed)

PM listed `roadmap_crud_ops.py`, `roadmap_crud_argparse.py`, and `tests/`. `roadmap_crud_argparse.py` needed no edits. Added `specy_road/bundled_scripts/roadmap_crud_chunk_report.py` so `roadmap_crud_ops.py` stays under the 400-line cap.

## Write paths during edit-node / add-node (each reaches the report)

Every `roadmap_crud*` disk write on these commands, and how it is named:

1. **`heal_before_mutation` → `auto_heal_roadmap`** — rewrites any healed chunk via `write_json_chunk`, and may rename a planning sheet when a missing task codename is derived. `heal_and_collect_paths` snapshots `roadmap/` and `planning/` around that pass and merges the changed rels into both `cmd_add` and `edit_node_set_pairs` reports (covers a heal in another chunk, and heal-side planning renames).
2. **`write_with_routing` (`add-node`)** — destination chunk; scaffolded planning sheet (`extra_files`); `roadmap/manifest.json` when a new chunk is created. `plan_add_chunk_writes` lists those paths.
3. **`write_node_update` (`edit-node`)** — edited chunk in place, or source remaining + destination (and manifest if the dest is new) on overflow; planning-sheet rename as unlink-source + write-dest. `plan_edit_chunk_writes` lists source, dest, manifest, and both rename paths.
4. **`claim_zones_following` (`edit-node --set touch_zones=`)** — `roadmap/registry.yaml` only when a claim row actually changes. `registry_rel_if_claim_touch_zones_change` adds that path; an unchanged registry stays out.

No other `roadmap_crud*` path writes a file on these commands. `ensure_codename_for_new_node` and `apply_set` are in-memory. `append_node_to_chunk` repeats the heal (idempotent after `cmd_add`'s first pass) and then `write_with_routing`, already covered.

## Behaviour

- **`edit-node`:** heal first, then plan touched paths (heal + overflow/relocation + rename + registry), write, print via `print_node_chunk_write_report`.
- **`add-node`:** heal first, then plan dest chunk / planning sheet / manifest plus heal paths; `write_with_routing` writes them.
- **In-place edit:** `read from` + `wrote` name the same chunk unless heal or a rename/registry write added paths.
- **Relocation:** `read from` source, `moved from` source `to` destination; commit list includes source, destination, and manifest when applicable.

## Verification

- `specy-road file-limits`
- `pytest tests/test_roadmap_crud_edit_node_chunks.py`
- `pytest tests/test_roadmap_crud.py tests/test_roadmap_crud_atomicity.py tests/test_roadmap_crud_edit_add_remove.py tests/test_roadmap_crud_edit_claim_zones.py`

## Added

- `roadmap_crud_chunk_report.py` — `NodeChunkWriteReport`, planners, `print_node_chunk_write_report`, `repo_rel`.
- `plan_edit_chunk_writes` — source/dest/manifest and both sides of a planning rename.
- `plan_add_chunk_writes` — chunk, planning sheet, manifest; `extra_paths` for heal.
- `print_node_chunk_write_report` — stdout format for A1.
- `registry_rel_if_claim_touch_zones_change` / `plan_edit_node_report` — registry path only when a claim row changes; heal paths merged here.
- `heal_and_collect_paths` / `snapshot_roadmap_files` / `changed_roadmap_rels` — pre-mutation heal files into the commit list.
- `edit_node_set_pairs` return value — `NodeChunkWriteReport`.
- Tests in `test_roadmap_crud_edit_node_chunks.py`: in-place, relocation, add-node, new chunk, planning rename, claim registry in/out, heal in another chunk.
- Removed `append_report_paths` (its empty-extra early return was unreachable); composition uses `_unique_commit_paths` at the two planners.
