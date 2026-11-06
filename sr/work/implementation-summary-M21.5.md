# Implementation summary — M21.5 `apply-restructure-ops`

## What changed

- **A1, new ops.** `apply` accepts `move-node`, `group-nodes`, `indent`, `outdent`, `remove-node` and `archive` alongside `add-node`, `edit-node` and `add-dependency`. Each entry is turned into argv and parsed by its own command's parser before anything runs: `roadmap_move_node.build_parser` (no subcommand), `roadmap_outline_group.build_parser` (indent / outdent / group-nodes, M21.2), `archive_cli.build_parser` (archive), and `roadmap_crud_argparse.build_parser` for the existing ops and `remove-node` (M21.4). The restructure ops take only `node`, `nodes`, `to_parent`, `into_new`, `title`, `type`, `id`, `fill_gaps` and `rewrite_refs`. Any other field (for example `index` or `deep`, which those parsers would take) refuses the file before any entry runs. `to_parent: null` is the root, like `parent_id: null`.
- **A2, one validation.** `roadmap_crud_ops.deferred_validation()` is a context manager that turns `run_validate_raise` into a no-op. Every command validates through `run_validate_raise`, including `AtomicWritePlan.commit` callbacks, `validate_callback` and `archive_ops.apply_archive`. `_run_changes` runs the entries inside it, then validates the final graph once. A failure there is a `ValueError`, and `_apply_in_place` then restores its snapshot. The snapshot (`_batch_paths`) now also covers `roadmap.md` and `roadmap-context.md`, which `archive` regenerates. `roadmap/` (registry and `archive/`) and the planning tops were already covered. Directories the batch created (`roadmap/archive/...`) are removed once they are empty. `_scratch_root` copies the same set, so a dry-run `archive` cannot write through a symlink into the live `roadmap.md`. `archive`'s `cmd_archive` returns an exit code and raises `ValueError`, so `_run_changes` handles a return code, `SystemExit` and `ValueError`.
- **A3, dry-run id map.** `id_map_lines(before, after)` composes the pre-batch → final id by `node_key`. It prints `Display ids changed (old -> new):` and one `  old -> new` line per surviving pre-batch node whose id changed, sorted by natural id. It then prints the existing wave lines. Created and removed nodes are omitted.
- **A4, tests and docs.** See `## Added`. `docs/roadmap-authoring.md` § Batch edits describes the new ops, their fields, the single validation, the restore set and the id map. It gives one inline YAML entry per new op. The file is at the 400-line cap, so the examples stay inside the existing paragraph. The `apply` help in `roadmap_crud_argparse.py` names the new ops and the id map.

## Touch zones (final list)

- `specy_road/bundled_scripts/roadmap_crud_dependency_ops.py`
- `specy_road/bundled_scripts/roadmap_crud_ops.py`
- `specy_road/bundled_scripts/roadmap_crud_argparse.py`
- `docs/roadmap-authoring.md`
- `tests/`
- **New, for the file-limits cap:** `specy_road/bundled_scripts/roadmap_apply_entries.py`. The effective policy is `sr/constraints/file-limits.yaml`, with 400 lines per file. `roadmap_crud_dependency_ops.py` was already at 400, so the entry-parsing half of `apply` moved into this module: `APPLY_OPS`, field handling, the per-op parser dispatch, `parse_change_file` and `id_map_lines`. Please add it to the zones.

No other file outside the zones changed. `roadmap_crud_delete.py` still imports `_scratch_root` unchanged. Its rehearsal now also copies the two generated files, which is harmless.

## Behaviour notes

- `parse_change_file(path)` dropped its unused `root` argument. Entries no longer get `--repo-root` at parse time, because `_run_changes` sets `ns.repo_root` and some parsers only take it after the subcommand. Nothing outside the module called `parse_change_file`.
- A refusal in the final validation reads `the batch's resulting roadmap does not validate; no change in the batch was applied`, followed by the validator's errors. The existing cycle test still finds `dependency cycle`.
- Validation warnings are printed once per batch, not once per entry.

## Verification

- `python -m pytest -q -n 4` → 5415 passed.
- `python specy_road/bundled_scripts/validate_file_limits.py` → OK.
- `ruff check specy_road tests` → clean.
- Red-green: with the deferral disabled, `test_a_regroup_applies_in_one_run_with_one_validation` fails with `assert 9 == 1`.

## Added

- `roadmap_crud_ops.deferred_validation` + `_VALIDATION_DEFERRED` + the early return in `run_validate_raise`: the in-process switch that defers per-command validation (A2).
- `roadmap_apply_entries.py` (new module): split out for the file-limits cap; holds the entry → argv → parser path.
- `RESTRUCTURE_FIELDS` + `_restructure_argv`: the allowed fields and argv for the new ops; refuses unknown fields before anything runs (A1).
- `_crud_argv`: the old ops' argv building lifted out of `_entry_argv` unchanged (ruff C901 complexity cap).
- `_parse_entry`: dispatches each op to its own command's parser and records `apply_op` for error messages (A1).
- `--to-parent` in `_option_argv`'s null branch: `to_parent: null` means the root, as `parent_id: null` does.
- `id_map_lines`: the composed dry-run `old -> new` map (A3).
- `_run_changes` return-code and `ValueError` branches: `archive`'s handler returns an exit code and raises `ValueError` instead of exiting.
- `_run_changes` final `run_validate_raise` call: the one validation per batch (A2).
- `_batch_paths`: adds `roadmap.md` / `roadmap-context.md` to the snapshot and the scratch copy (A2).
- `_dirs_under` + empty-directory pruning in `_restore`: a rolled-back first archive leaves no empty `roadmap/archive/` behind.
- Test `test_dry_run_prints_the_composed_id_map_before_the_waves`: A3 map composed across group/move/indent/outdent/remove, with created nodes omitted, printed before the waves, nothing written.
- Test `test_a_regroup_applies_in_one_run_with_one_validation`: A4 regroup in one run. It wraps the public `roadmap_crud_ops.validate_at` with a counter because "one validation" is the acceptance criterion itself.
- Test `test_a_refused_entry_after_an_archive_restores_everything`: A4 archive followed by a refusing entry restores every file, generated files included.
- Parametrized cases in `test_a_malformed_entry_is_refused_before_anything_runs` (move-node `index`, indent with `to_parent`, group-nodes without `nodes`, archive `deep`): unknown field and parser refusals for the new ops (A1).
- Mocks: none besides the `validate_at` counter above.
