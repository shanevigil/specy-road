# Implementation summary — M11.10 `edit-node-add-remove`

## What changed

`specy-road edit-node` takes `--add KEY=ENTRY` and `--remove KEY=ENTRY` (both repeatable) for the list fields `acceptance`, `risks`, `touch_zones` and `dependencies`. `--set` is no longer required; at least one of `--set`, `--add` or `--remove` is.

- **A1.** `expand_list_edits` (in `roadmap_crud_argparse.py`) reads the node's current list, appends or drops the named entries, and turns each touched field into the whole list as repeated `--set key=item` values. `cmd_edit` then runs unchanged: same `merge_set_pairs`, the same validation and atomic write. `touch_zones` values split on commas, as `--set` does. `dependencies` values accept a node_key or a display id through the existing `resolve_dependency_refs`, as `add-dependency` does. An `acceptance` entry is taken whole, commas included.
- **A2.** The expanded pairs reach `edit_node_set_pairs` as a `touch_zones` pair, so `claim_zones_following` rewrites a claimed leaf's registry row exactly as it does for `--set` (M10.14). A test checks the claim after both an add and a remove.
- **Duplicate add / missing remove.** Either one leaves the list as it is and prints `[note] <id> already lists|does not list <field> entry '<x>'; left as is` to stderr. This matches `add-dependency` / `remove-dependency`, which also treat these cases as an ok no-op, so a re-run script stays idempotent. If that leaves nothing to write and there is no `--set`, the command prints `[ok] <id> unchanged` and touches no file (no chunk re-render, no registry write).
- **Refusals (nothing written):** `--add`/`--remove` on a non-list field, an empty entry, `--set` and `--add`/`--remove` of the same field in one command, and an edit with no `--set`, `--add` or `--remove` at all.
- `docs/roadmap-authoring.md`: the `touch_zones`, `dependencies`, `acceptance` and `risks` rows name the new flags, the no-op behaviour, and that removing a criterion renumbers those after it.

## Where the merge lives, and why

The planning sheet asked for the list merge in a helper because `roadmap_crud_ops.py` is near its cap. It sits at 398/400 lines, so even a helper function there breaks `file-limits`. A new module would fall outside the touch zones, and the finish gate would flag it. So the merge is a CLI-level expansion in `roadmap_crud_argparse.py` (277 → 357 lines), wired as edit-node's `func` (`_cmd_edit_node` → `expand_list_edits` → `cmd_edit`). `roadmap_crud_ops.py` is unchanged.

The read-then-write follows the pattern `cmd_add_dependency` already uses (read the merged node, then call the edit path). `apply` dispatches through `ns.func`, so its `edit-node` entries now pass through the wrapper too. With only `set:` they go straight to `cmd_edit` as before.

## Touch zones (confirmed)

Changed: `specy_road/bundled_scripts/roadmap_crud_argparse.py`, `docs/roadmap-authoring.md`, `tests/test_roadmap_crud_edit_add_remove.py`. `specy_road/bundled_scripts/roadmap_crud_ops.py` stays in the zones but was not edited, for the cap reason above.

## Verification

- `python -m pytest -q tests/test_roadmap_crud_edit_add_remove.py` — 9 passed
- `python -m pytest -q tests/test_roadmap_crud_edit_add_remove.py tests/test_roadmap_crud_edit_claim_zones.py tests/test_roadmap_crud.py tests/test_roadmap_apply.py tests/test_roadmap_crud_atomicity.py tests/test_node_routing_fields.py` — 67 passed
- `python -m pytest -q tests/test_roadmap_crud_dependencies.py tests/test_archive_dependencies.py` — 16 passed
- `specy-road file-limits` — OK
- `ruff check` on the changed Python files — clean
- `python -m pytest -q` (full suite) — 2964 passed, 2 skipped in 27:33

## Added

### Helpers
- `_list_entries` (roadmap_crud_argparse.py): maps one `--add`/`--remove` value to the stored entries: comma split for `touch_zones` (as `--set` does), id → node_key for `dependencies`.
- `expand_list_edits` (roadmap_crud_argparse.py): the list merge. Reads the current list and expands touched fields into full `--set` lists so `cmd_edit`'s validation and claim-row sync apply unchanged.
- `_cmd_edit_node` (roadmap_crud_argparse.py): edit-node's `func`. Reports expansion errors as `error:` and exit 1, prints `[ok] … unchanged` when nothing is left to write, and otherwise calls `cmd_edit`.

### Branches / guards
- Refuses a non-list field or an empty entry for `--add`/`--remove`, so an entry is never silently dropped or a scalar never turned into a list.
- Refuses `--set` and `--add`/`--remove` of the same field in one command: the expanded list would otherwise silently replace the `--set` value.
- Refuses an edit with no `--set`/`--add`/`--remove`, which replaces argparse's `required=True` on `--set`.
- Duplicate add / missing remove → note and no change, so re-runs stay idempotent, as with `add-dependency`/`remove-dependency`.
- Nothing changed and no `--set` → `[ok] unchanged` without calling `cmd_edit`, so a no-op does not re-render the chunk or touch the registry.
- An unknown node id → the existing `unknown_node_msg` error.

### Argparse
- `--add`, `--remove` on `edit-node` (append, `KEY=ENTRY`); `--set` no longer `required=True`.

### Mocks
- none

### Tests (`tests/test_roadmap_crud_edit_add_remove.py`)
- `test_add_and_remove_a_zone_keep_the_rest_and_the_claim_follows`: A1 + A2. Adding and removing a zone keep the other entries, and the claim row follows both.
- `test_acceptance_entries_add_and_remove`: A1 for acceptance, including an entry that contains a comma.
- `test_dependencies_take_an_id_or_a_key`: A1 for dependencies. Adds by display id (stored as the key) and removes by key.
- `test_duplicate_add_leaves_the_list_and_writes_nothing`: A2 duplicate add. Note printed, `[ok] unchanged`, chunk and registry bytes unchanged.
- `test_removing_a_missing_entry_leaves_the_list`: A2 missing remove. Note printed, and the other edit in the same command still applies.
- `test_bad_list_edits_are_refused_before_writing` (4 cases): non-list field, empty entry, `--set`+`--add` on the same field, no edit flags. Each one exits non-zero and leaves the chunk unchanged.
