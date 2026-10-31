# Implementation summary: M10.14 — edit-node keeps an active claim's touch zones in step

## Summary

`edit-node --set touch_zones=…` (and every other `edit_node_set_pairs` caller, including the PM GUI's node edit) now rewrites the `touch_zones` of any `roadmap/registry.yaml` row claiming that node to the node's new list. It happens in the same command, inside the edit's transaction, and the CLI prints one `[note]` line naming the claim. An edit that does not set `touch_zones`, or one on a node with no claim, leaves the registry byte-for-byte alone. The review packet and the finish implementation check already read the claim row first, so both see the new zones with no further step.

## Changes

- `specy_road/bundled_scripts/registry_claim_zones.py` (new): `rewrite_claim_zones` sets the list on matching rows. The `claim_zones_following` context manager reads the registry with `read_registry`, stages the rewrite in an `AtomicWritePlan` serialized with `dump_registry_text` (the same serializer `write_registry` uses), and writes it before the chunk write. The edit's own validation therefore sees both files. If the chunk write is rejected, the rewrite is rolled back, and the note is printed only after the edit succeeds.
- `specy_road/bundled_scripts/roadmap_crud_ops.py`: `edit_node_set_pairs` wraps `write_node_update` in `claim_zones_following`, passing the node's zones only when `touch_zones` was among the pairs. I collapsed the `write_node_update` call onto one line so the file stays at 398 lines (cap 400).
- `specy_road/finish_implementation_check.py`: the "fix the zones" hint says edit-node also rewrites the claim's registry row, which finish reads first. That is why edit-node alone is enough (A3).
- `docs/dev-workflow.md`: added one bullet under *Multi-agent coordination*. It says editing a claimed leaf's zones updates its claim, and that both files should be committed on the integration branch.
- `tests/test_roadmap_crud_edit_claim_zones.py` (new): tests for A1 and A2 (see Added).

**`_rewrite_touch_zones` reuse (A4):** I did not reuse it, because the shapes don't fit. That function renames path *segments* through an old→new id map on every row. An edit replaces one claim's whole list with the node's. Calling it here would mean building a fake segment map, and that cannot express a widening. `roadmap_move_node.py` is unchanged. The two share the registry module (`registry_yaml`) and nothing else.

**Touch zones (final):** `specy_road/bundled_scripts/roadmap_crud_ops.py`, `specy_road/bundled_scripts/registry_claim_zones.py`, `specy_road/finish_implementation_check.py`, `docs/dev-workflow.md`, `tests/test_roadmap_crud_edit_claim_zones.py`. `roadmap_move_node.py` was listed but did not need a change. Two places outside the zones repeat the old hint and were left as they are: `docs/git-workflow.md` (the `require_implementation_before_finish` paragraph) and `specy_road/bundled_scripts/finish_task_args.py` (the `--allow-empty-implementation` help). Both are still accurate, since edit-node is still the fix.

## Verification

- `pytest tests/test_roadmap_crud_edit_claim_zones.py` → 6 passed. With the original `roadmap_crud_ops.py` restored, 3 fail (claim rewrite and note, packet, finish). The other 3 are guards that pass either way: no-zones edit, unclaimed node, rollback.
- `pytest tests/test_roadmap_crud_edit_claim_zones.py tests/test_move_node_cli.py tests/test_finish_implementation_check.py tests/test_review_packet.py tests/test_roadmap_crud*.py` → 90 passed.
- `pytest` (full suite) → 2548 passed, 2 skipped.
- `specy-road file-limits` → OK. `ruff check` on the changed Python files → all checks passed.

## Added

### Helpers
- `registry_claim_zones.rewrite_claim_zones`: sets `touch_zones` on the rows claiming a node and returns the codenames it changed, so the caller can name them (A1).
- `registry_claim_zones.claim_zones_following`: a context manager that writes the claim rewrite before the chunk write and rolls it back if that write raises. This keeps the claim and node in one validated transaction without changing `roadmap_chunk_router.write_node_update`, which is outside the touch zones.

### Branches / guards
- `zones is None` → registry untouched: an edit that did not set `touch_zones` must not rewrite a claim (A1, "unchanged in behaviour").
- `if not changed: yield; return`: no claim, or a claim already equal to the node's list, means no write and no note.
- `isinstance(entries, list)` / `isinstance(entry, dict)`: tolerate a malformed registry the same way `move-node`'s `_stage_registry_ids` does. Validation reports the malformation, not this helper.
- `except BaseException: plan.rollback(); raise`: a rejected edit leaves the registry as it was.

### Mocks
- `monkeypatch.setattr(roadmap_chunk_router, "write_node_update", reject)` in the rollback test: it forces the chunk write to fail after the claim rewrite has landed, which shows the rewrite is undone.

### Tests
- `test_edit_rewrites_claim_zones_and_names_the_claim`: A1, the row is rewritten and exactly one line names the claim.
- `test_edit_without_zones_leaves_the_claim_alone`: A1, an edit that does not set zones does not touch the registry.
- `test_edit_of_an_unclaimed_node_leaves_the_registry_alone`: A1, a node without a claim behaves as before.
- `test_rejected_edit_rolls_the_claim_back`: transaction guard for the new write.
- `test_packet_reads_widened_zones`: A2, after widening on dev, `docs/x.md` is no longer flagged outside touch zones in the packet.
- `test_finish_check_reads_edited_zones`: A2/A3, the finish gate judges the claim's edited zones, and its hint says edit-node rewrites the claim.
