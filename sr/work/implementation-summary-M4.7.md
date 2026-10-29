# Implementation summary for M4.7

## Summary

`specy-road apply CHANGES.yaml [--dry-run]` runs a file of `add-node`, `edit-node` and `add-dependency` entries as one batch (A1, A2). `add-node --acceptance` is repeatable, and `add-node --dependency` / `add-dependency` take a display id or a node_key and store the node_key (A3).

- **Change file.** A YAML list, or `changes: [...]`. Each entry is `op:` plus that subcommand's long options (snake_case or kebab-case; `dependencies` / `touch_zones` alias the singular flags). `node:` and `dependency:` fill the positionals. `edit-node` takes `set: {field: value | [values]}`, and a list repeats the option. Every entry goes through the real `roadmap_crud` subparser **before anything runs**, so an unknown op, a missing `node:`, an option the command does not take, or a bad `--type` refuses the file with nothing written.
- **Atomic apply (A2).** Entries run in order through the existing commands (`cmd_add`, `cmd_edit`, `cmd_add_dependency`), so each keeps its own validation, milestone lock, codename derivation, chunk routing and planning-sheet scaffold. Each command commits its own transaction (the router chooses a chunk from what the previous write left on disk, the reason `promote` gives for not batching). So the batch snapshots every file under `roadmap/` and each planning sheet's top folder, then restores that byte-for-byte (new files unlinked) if any entry refuses. The commands' `[ok]` lines are held back until the whole batch succeeds, so a refused batch does not print `[ok]` for work it rolled back. That is the defect the triage note records for `accept A B …`.
- **Dry run (A1).** Rehearses the same commands on a scratch root in a temp dir: `roadmap/` and the planning folders are copied, every other top-level entry is symlinked (copied where symlinks are unavailable), and `.git` is left out. It then prints the resulting waves. Nothing is written to the checkout. Both modes print `wave N: …`, `Ready now: …`, `Blocked: X waiting on …` and `Unauthored: …`, computed by `session_plan.compute_session_plan` with `unauthored_leaves` (the same pure function `grind-session --plan` uses).
- **Display ids (A3).** `resolve_dependency_refs` keeps a live or archived node_key as given and maps a display id to its key. Anything else is refused with `dependency 'X' is neither a node id nor a node_key in the roadmap`, before any write. This is what lets a batch wire dependencies to nodes it creates, whose keys it cannot know yet.

Limits, all deliberate and kept small:

- `edit-node --set dependencies=…`, `set-dependencies` and `remove-dependency` still take node_keys only. A3 names `--dependency` and `add-dependency`, and the docs say which takes which.
- The dry run sits outside git, so `review_required` reads the review switch from the working tree only, not also from the integration branch. That matters only for the pre-existing registry check, and only when the two disagree.
- Entries apply in order: add a node before an entry that depends on it.

## Changes

- `specy_road/bundled_scripts/roadmap_crud_dependency_ops.py`: adds `resolve_dependency_refs`, `add-dependency` resolves its DEP, and adds the `apply` implementation (parse, run, snapshot/restore, scratch root, wave preview, `cmd_apply`).
- `specy_road/bundled_scripts/roadmap_crud_argparse.py`: adds the `apply` subparser, `add-node --acceptance`, and help text for `--dependency` and `add-dependency DEP`.
- `specy_road/bundled_scripts/roadmap_crud_ops.py`: `cmd_add` stores `acceptance` and resolves `--dependency` refs. A 5-line comment is condensed to 2 so the file stays at the 400-line cap.
- `specy_road/cli.py`: `apply` joins `_CRUD_COMMANDS`.
- `specy_road/cli_usage.py`: `apply`, `--acceptance`, display-id deps, `add-dependency <DEP>`.
- `docs/roadmap-authoring.md`: quickstart bullets, the `dependencies` and `acceptance` field rows, the Tooling list, and a new "Batch edits (`apply`)" section.
- `tests/test_roadmap_apply.py`: new.
- Review fix (gpt-5.6-sol-high block on `e62d652`): `tests/test_roadmap_crud.py` renames its shared helpers `_fixture_repo` → `crud_fixture_repo` and `_run_crud` → `run_crud`. Its importers (`test_roadmap_apply.py`, `test_roadmap_crud_dependencies.py`, `test_roadmap_edit_fields.py`, `test_scaffold_planning.py`) follow, so no test imports a `_`-prefixed name from another module. This is a pure rename with no behaviour change. The unrelated local `_fixture_repo` in `test_roadmap_crud_ops.py` and `_run_crud` in `test_set_gate_status.py` are module-private and untouched.

**Touch zones, final list:** the given zones minus `session_plan.py`, which was reused unchanged. Used: `roadmap_crud_argparse.py`, `roadmap_crud_ops.py`, `roadmap_crud_dependency_ops.py`, `cli.py`, `cli_usage.py`, `docs/roadmap-authoring.md`, `tests/`.

**Proposed zone change (not made):** the `apply` code would read better in its own `specy_road/bundled_scripts/roadmap_crud_apply.py`. It is not a dependency op, and `roadmap_crud_ops.py` is at its 400-line cap. That path is outside the touch zones, so the code lives in `roadmap_crud_dependency_ops.py` (now ~375 lines), and the module docstring says why. A follow-up could move it as a pure relocation.

## Verification

- `pytest tests/test_roadmap_apply.py`: 14 passed.
- After the review fix: `pytest tests/test_roadmap_apply.py tests/test_roadmap_crud.py tests/test_roadmap_crud_dependencies.py tests/test_roadmap_edit_fields.py tests/test_scaffold_planning.py`: 49 passed.
- Re-run on the review fix (`c3536ad`): full `pytest` 2254 passed, 2 skipped, 2 failed (the same two `test_review_round6_evidence.py` failures as below); `ruff`, `validate_file_limits.py`, `check_test_private_imports.py` (118/118, 0 new), `check_clones.py` (12/12, 0 new), dogfood `validate` and `export --check` all OK. No `_`-prefixed name is imported from `tests.test_roadmap_crud` any more.
- `pytest` (full suite): 2254 passed, 2 skipped, 2 failed. Both failures are in `tests/test_review_round6_evidence.py`, which calls `review_packet._changed`; that function does not exist at base `d13ed8d`. Neither file is in this diff or the touch zones, so they fail without this change and were left alone.
- `python specy_road/bundled_scripts/validate_roadmap.py --repo-root tests/fixtures/specy_road_dogfood`: OK.
- `python specy_road/bundled_scripts/export_roadmap_md.py --check --repo-root tests/fixtures/specy_road_dogfood`: OK.
- `python specy_road/bundled_scripts/validate_file_limits.py`: OK.
- `ruff check specy_road tests scripts`: all checks passed.
- `python scripts/check_clones.py` (pylint 4.1.3 in a scratch venv): 12 current, 12 baselined, 0 new.
- `python scripts/check_test_private_imports.py`: 0 new.
- Manual run on a copy of the dogfood fixture: `apply --dry-run` printed the waves, and a `shasum` of every file before and after was identical. A batch whose 2nd entry referenced `M404` exited 1 and the tree was again identical. The real apply passed `validate`.

## Walkthrough

1. Copy `tests/fixtures/specy_road_dogfood` somewhere and write a `changes.yaml` like the example in `docs/roadmap-authoring.md` ("Batch edits").
2. `python -m specy_road.cli apply changes.yaml --dry-run --repo-root <copy>`: waves are printed and `git status` / checksums are unchanged.
3. Change one entry's dependency to `M404` and run without `--dry-run`: exit 1, `change N (add-dependency) failed; no change in the batch was applied`, and no `[ok]` lines.
4. Fix it and run without `--dry-run`, then `show-node`: the new nodes carry their `acceptance`, and their `dependencies` hold node_keys.

## Added

- `resolve_dependency_refs` (dependency_ops): maps display ids to node_keys and refuses unknown refs before writing (A3).
- add-dependency `try/except ValueError` around the resolver: prints `error:` and exits 1 like the command's other refusals.
- `cmd_add` `acceptance` field (strip, drop blanks, omit when empty): the schema requires `minItems: 1` and non-empty items (A3).
- `cmd_add` lazy import of `resolve_dependency_refs`: `roadmap_crud_dependency_ops` imports `roadmap_crud_ops` at module load, so a top-level import would be circular.
- `APPLY_OPS` / `_OPTION_ALIASES`: the three ops A1 names; aliases so change files can use node field names (`dependencies`, `touch_zones`).
- `_option_argv`: entry option → CLI flag(s). A `bool` becomes a bare flag (`sync_codename`), `parent_id: null` becomes `null` (phase root), and any other null is skipped as unset.
- `_entry_argv`: entry → subcommand argv, with guards for an unknown op, a missing `node:`/`dependency:`, and a missing or empty `set:`.
- `parse_change_file`: parses every entry with the real subparser before anything runs. It guards an unreadable file or YAML, an empty or non-list document, and argparse's `SystemExit` (re-raised as a numbered `ValueError`).
- `_run_changes`: runs entries in order, turns a non-zero `SystemExit` into `change N (op) failed…`, and holds stdout back so rolled-back `[ok]` lines are never printed.
- `_graph_paths`: what a batch can write (`roadmap/`, `planning/`, each planning_dir's top folder). It skips unsafe planning_dir values so a `..` can never widen the snapshot.
- `_files_under` / `_restore`: the batch snapshot and its byte-exact restore (A2).
- `_apply_in_place`: snapshot → run → restore on any `BaseException` (A2).
- `_scratch_root`: the temp rehearsal root for `--dry-run`. It has a symlink→copy fallback for platforms without symlink privilege and leaves `.git` out so nothing can reach the real index (A1, "without writing").
- `wave_preview`: ready/blocked/waves via `compute_session_plan` + `unauthored_leaves` (A1).
- `cmd_apply`: the CLI entry, with `ValueError` → `error:` + exit 1.
- `_p_apply` subparser, plus `--acceptance` and the `--dependency` / `DEP` help: CLI surface for A1–A3.
- `"apply"` in `_CRUD_COMMANDS`: dispatches `specy-road apply`.
- `crud_fixture_repo` / `run_crud` (renamed, not new): public names for the shared CRUD test helpers, so the new test does not import private names (review fix).
- Mocks: none.
- Tests (`tests/test_roadmap_apply.py`):
  - `test_add_node_acceptance_is_repeatable`: A3, repeatable `--acceptance`.
  - `test_add_node_dependency_takes_a_display_id_and_stores_the_key`: A3, mixed id and key refs stored as keys.
  - `test_add_node_unknown_dependency_is_refused_before_writing`: A3, unknown ref refused with the tree unchanged.
  - `test_add_dependency_takes_a_display_id`: A3, `add-dependency` with a display id.
  - `test_dry_run_validates_prints_waves_and_writes_nothing`: A1, the waves, ready and blocked lines, with every file byte-identical and no sheets.
  - `test_apply_writes_the_whole_batch`: A2, nodes, acceptance, keyed deps and sheets written.
  - `test_a_refused_change_rolls_back_the_changes_before_it`: A2, the 4th entry fails, the first three are undone, and no `[ok]` is printed.
  - `test_a_dependency_cycle_is_refused_as_a_whole`: A2, a graph-level validation failure rolls back the batch.
  - `test_a_malformed_entry_is_refused_before_anything_runs` (4 cases): unknown op, missing node, missing set, unknown option. Each is refused at parse time even though entry 1 is valid.
  - `test_an_empty_change_file_is_refused`: empty-document guard.
  - `test_top_level_cli_dispatches_apply`: `specy-road apply` through `cli.main`, with `--repo-root` after the subcommand.
