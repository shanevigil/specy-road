# Implementation summary — M16.1.10

Public scenarios for outline moves, edit-field setters, archive, scaffold and update, written before the CRUD fold. No package file changed. A scenario that failed would have been `xfail(strict=True)` naming a new leaf; none failed.

## Touch zones

Confirmed: `tests/scenarios/roadmap_edit/` only. Three new files, no other path. No zone needs adding or removing.

## Acceptance

**A1.** `tests/scenarios/roadmap_edit/` drives each listed scenario through a public function or a CLI entry point:

- Indent, outdent and reparent, including the refusals: `apply_indent`, `apply_outdent`, `move_node_outline` in `test_outline.py`.
- One `apply_set` row per `EDIT_WHITELIST` key, plus the setter refusals: `test_edit_fields.py`.
- `archive --auto` (nothing old enough, and a leaf complete past the threshold) and the restore errors (unknown id, dry-run unknown id, missing chunk): `archive_cli.main` in `test_archive_scaffold_update.py`.
- `scaffold-planning` for a missing sheet and for `--force`: `scaffold_planning.main`.
- Update fast-forward of a clean clone, and the dirty-tree refusal: `update_specy_road.main`.

**A2.** Green with no package change. `pytest -n 4 tests/scenarios/roadmap_edit`: 62 passed. The same tests inside the full suite: 6949 passed, 14 skipped. No `xfail`.

**A3.** Line and branch coverage of the modules this sheet names, measured with coverage 7.17.2, branch measurement and the subprocess patch from `pyproject.toml`, `pytest -n 4`. Before is that suite with `tests/scenarios` left out (6887 passed, 14 skipped). After is the suite with these tests included. Not a pass/fail number. The five files together are not the suite TOTAL, so their percent is not the `fail_under` floor.

| Module | Lines before | Lines after | Branches before | Branches after |
| --- | --- | --- | --- | --- |
| `archive_cli.py` | 73% (112/154) | 86% (132/154) | 55% (22/40) | 78% (31/40) |
| `roadmap_edit_fields.py` | 78% (163/210) | 97% (203/210) | 70% (78/112) | 92% (103/112) |
| `roadmap_outline_ops.py` | 90% (93/103) | 98% (101/103) | 77% (34/44) | 93% (41/44) |
| `scaffold_planning.py` | 85% (61/72) | 86% (62/72) | 60% (12/20) | 65% (13/20) |
| `update_specy_road.py` | 69% (128/185) | 74% (136/185) | 52% (32/62) | 56% (35/62) |

**A4.** Estimated about +300 test lines. Actual 543 lines in the three new files. Informational.

`python scripts/lean_metrics.py --check` deltas are recorded by this leaf's READY `--run`, after this summary is committed, because the script counts tracked files.

## Added

### Helpers

- `set_type` — rewrite one fixture node's type so a gate refusal can be arranged.
- `_key` — fixture `node_key` for a display id, so reparent scenarios can call `move_node_outline`.
- `fresh_node` — a task whose codename was chosen, so a title edit does not also rewrite the codename.
- `set_field` — `apply_set` with the fixture's ids and node keys.
- `SETTER_ROWS` — one stored value per `EDIT_WHITELIST` key.
- `_close_leaf` — mark a leaf Complete with an old `closed_at` so `archive --auto` can see it.
- `_exit` — an in-process CLI `main`'s `SystemExit` as an int.
- `_archive` — `archive_cli.main` with `--repo-root`.
- `_live_ids` — display ids still in the loaded graph.
- `_scaffold` — `scaffold_planning.main` via `sys.argv`, because that entry point has no argv parameter.
- `_git` — git with a throwaway identity, for the update clone.
- `clone_behind_origin` — a local bare `origin` one commit ahead, so fast-forward does not use GitHub.

### Branches or guards

- In `test_each_setter_writes_its_field`, the `title` row also asserts the hand-picked codename is kept, and the `codename` row also asserts `planning_dir` follows the new slug.

### Mocks

- `monkeypatch` of `update_specy_road.is_canonical_specy_road_remote` — the fast-forward remote is a local bare repo, not `github.com/shanevigil/specy-road`. The patch lets `main` reach the fast-forward and the dirty-tree refusal. No call-count assertion.
- `monkeypatch` of `sys.argv` in `_scaffold` — `scaffold_planning.main` parses `sys.argv`.

### Tests

- `test_indent_nests_the_node_under_the_previous_sibling` — indent moves M1.3 under M1.2 and renumbers only that node.
- `test_outdent_places_the_node_after_its_former_parent` — outdent moves M1.2.4 up beside M1.2.
- `test_reparent_moves_the_node_under_the_named_parent` — `move_node_outline` places M1.3 first under M2.
- `test_a_shift_that_cannot_happen_writes_nothing` — indent of the first sibling, outdent of a root, indent under a gate, and indent of a gate under a task all return no map and write nothing.
- `test_a_shift_of_an_unknown_id_raises` — indent and outdent of an unknown id raise and write nothing.
- `test_reparent_of_an_unknown_node_raises` — an unknown `node_key` raises and writes nothing.
- `test_reparent_validation_error_leaves_the_tree` — unknown parent, move under itself, move under a descendant, and an index past the siblings.
- `test_reparent_refuses_an_illegal_gate_move` — under a gate, a gate at the root, and a gate under a task.
- `test_the_setter_table_has_one_row_per_whitelisted_key` — the row keys are exactly `EDIT_WHITELIST`.
- `test_each_setter_writes_its_field` — each whitelist key stores the value for that setter.
- `test_parent_id_null_clears_the_parent` — `parent_id=null` stores `None`.
- `test_a_setter_refuses_a_value_the_field_does_not_allow` — type, parent, status, decision status, codename, execution milestone, integers, routing tags, dependency and an unknown key.
- `test_archive_auto_with_nothing_old_enough_writes_nothing` — `--auto` with nothing past the threshold leaves the graph and writes no archive.
- `test_archive_auto_archives_a_leaf_complete_past_the_threshold` — `--auto` archives that leaf and records it.
- `test_restore_of_an_unknown_id_is_an_error` — restore of an unknown id exits 1 and names `list-archives`.
- `test_restore_dry_run_of_an_unknown_id_is_an_error` — the dry-run unknown-id path exits 1 without the list-archives hint.
- `test_restore_of_a_record_whose_chunk_is_missing_changes_nothing` — a record whose chunk file is gone is refused and the archive index stays.
- `test_scaffold_planning_writes_a_missing_sheet` — a missing sheet is created and `planning_dir` is set, with no display id in the body.
- `test_scaffold_planning_force_overwrites_an_existing_sheet` — without `--force` the sheet is kept; with `--force` it is replaced by the template.
- `test_update_fast_forwards_a_clean_clone` — a clean clone moves to the remote tip.
- `test_update_refuses_a_dirty_tree` — a dirty tree exits 1 and the dirty file stays.
