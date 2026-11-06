# Implementation summary: M21.19 (apply-dry-run-rebases-links)

Base `8c0c042e`; fix commit `bfe8a90a`.

## What changed

- **A1:** `_scratch_root` (`roadmap_crud_dependency_ops.py`) now calls `_rebase_graph_symlinks(scratch, root.resolve())` before it yields, so `apply --dry-run` and `remove-node --dry-run` use the same rebase. `rehearsal_root` (`roadmap_crud_delete.py`) now only yields `_scratch_root`. `_rebase_graph_symlinks` and `_scratch_target` stay in `roadmap_crud_delete.py` with their rule unchanged (only the docstring now says "a real run" instead of "real removal"). `_scratch_root` imports the function inside its body, the same way `rehearsal_root` already imports `_scratch_root`, so there is no import cycle. I first moved the function next to `_scratch_root`, but that pushed `roadmap_crud_dependency_ops.py` to 423 lines, over the 400-line cap in `sr/constraints/file-limits.yaml` that a bare `specy-road file-limits` reads. The brief allows importing it instead, so no new module was needed. `tests/test_remove_node.py` passes and was not changed.
- **A2:** `apply_archive` (`archive_ops.py`) calls the new `_refuse_links_out` first, before any write or move. It checks the archive chunk (`roadmap/archive/chunks/<id>.json`), the archive index (`roadmap/archive/index.json`) and each sheet's `origin` and `stored` path with `managed_block.resolves_outside(root, root / rel)`. On a hit it raises `ValueError("refusing to archive: <rel> resolves outside <root>")`.
- **A3 needed one more archive change.** With the rebase in place, a dry run of an archive whose sheet is an in-repo absolute link moves the scratch copy's target file. That left the `planning/` link dangling, and validation then refused the batch: "orphan planning file planning/M99.1_…md". The real apply would have refused it the same way and rolled back. A3 requires exit 0, so `_move_planning_sheets` now deletes the origin link after moving the file it points to. Nothing else about the move changed.
- **A3 tests** (`tests/test_roadmap_apply.py`, all through the CLI):
  - In-repo sheet link (the target is under `roadmap/store/`, because `planning/` may not have subdirectories): the dry run exits 0, live bytes are unchanged, and the link and its target are still there.
  - Sheet linked outside the repo, and `roadmap/archive` linked to an outside directory: the dry run exits 1, stderr names the path and says "resolves outside", and the live tree, the outside bytes and the outside directory listing are unchanged.
  - The existing archive-then-refused-entry test is now parametrized over real apply and `--dry-run`.
  - The `in-repo-abs-dir-link` layout with an edit-node title change: the dry run exits 0 with live bytes unchanged; the real apply exits 0, the link is kept, and the new title is in `roadmap/storage/T.json`.
- **A4:** CHANGELOG `[Unreleased]` → Fixed entry.
- **A5:** net change: package about +25 lines, tests about +80.

## Touch zones

All edits are within the listed zones; no other file needed a change. The callers of `archive_ops` outside the zones (`archive_cli`, `gui_app_routes_archive`, the archive tests) get the new refusal through `apply_archive`, and the full suite passes.

## Verification

- `python -m pytest tests/test_roadmap_apply.py tests/test_remove_node.py -q`: pass
- `python -m pytest -n 4 -q` (full suite): 5425 passed
- `specy-road file-limits`: OK
- `ruff check` on the changed files: clean
- Red/green check: with the `specy_road/` changes stashed, 4 of the new or changed cases in `tests/test_roadmap_apply.py` fail: the in-repo sheet link, both link-out layouts, and the dry-run case of the chunk-directory link. The dry-run case of the refused-after-archive test passes either way, because its fixture has no links; it is there as the acceptance row.

## Added

- `archive_ops._refuse_links_out`: the A2 check that runs before any write or move, covering every sheet source and archive output.
- Guard in `archive_ops._move_planning_sheets` that deletes the origin link after moving its target: without it, the in-repo sheet-link dry run in A3 fails validation as an orphan sheet.
- `_scratch_root` now calls `_rebase_graph_symlinks` (A1). The call in `rehearsal_root` was removed.
- Test helper `_complete_m99_1`: taken out of the existing archive test so the new archive tests can reuse it.
- Test helper `_sheet_m99_1`: finds M99.1's planning sheet for the link layouts.
- Test layouts `_sheet_links_out` and `_archive_dir_links_out`: the two link-out rows in A3.
- Test `test_dry_run_archive_of_an_in_repo_sheet_link_leaves_the_live_sheet`: the data-loss regression (F4).
- Test `test_dry_run_archive_through_a_link_out_is_refused` (2 cases): the refusals for a sheet and for the archive directory linked outside.
- Test `test_apply_through_an_in_repo_absolute_chunk_dir_link` (dry-run and real): the case where apply's dry run and real run disagreed (W1).
- Parametrization of `test_a_refused_entry_after_an_archive_restores_everything` with `--dry-run`: the A3 row for a rehearsal refused after an archive entry.
- Mocks: none.
