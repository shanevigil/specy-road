# Implementation summary — M21.5 `apply-restructure-ops`

## What changed

- **A1, new ops.** `apply` accepts `move-node`, `group-nodes`, `indent`, `outdent`, `remove-node` and `archive` alongside `add-node`, `edit-node` and `add-dependency`. Each entry is turned into argv and parsed by its own command's parser before anything runs: `roadmap_move_node.build_parser` (no subcommand), `roadmap_outline_group.build_parser` (indent / outdent / group-nodes, M21.2), `archive_cli.build_parser` (archive), and `roadmap_crud_argparse.build_parser` for the existing ops and `remove-node` (M21.4). The restructure ops take only `node`, `nodes`, `to_parent`, `into_new`, `title`, `type`, `id`, `fill_gaps` and `rewrite_refs`. Any other field (for example `index` or `deep`, which those parsers would take) refuses the file before any entry runs. `to_parent: null` is the root, like `parent_id: null`.
- **Fix round 1 (gpt-6.1-sol-low block).** Class: a field whose value adds no argv (`false`, `null`, `[]`) was dropped by `_option_argv` before argparse could see its name, so an unknown field, or a restructure field the chosen command does not take (`indent` with `to_parent: false`), was accepted. Design change: `_parse_entry` now applies one rule to every non-positional field of every op. The name must be a long option of the entry's own command (read from that command's parser, `--help` excepted), and for restructure ops it must also be in `RESTRUCTURE_FIELDS`. The name is checked before its value is converted. The old `_crud_argv` / `_restructure_argv` / `_entry_argv` split became one `_positional_argv` table (`_POSITIONALS`) plus that rule. The refusal reads `change N: not a valid <op>: no field '<key>' (its options: ...)`.
- **A2, one validation.** `roadmap_crud_ops.deferred_validation()` is a context manager that turns `run_validate_raise` into a no-op. Every command validates through `run_validate_raise`, including `AtomicWritePlan.commit` callbacks, `validate_callback` and `archive_ops.apply_archive`. `_run_changes` runs the entries inside it, then validates the final graph once. A failure there is a `ValueError`, and `_apply_in_place` then restores its snapshot. The snapshot (`_batch_paths`) now also covers `roadmap.md` and `roadmap-context.md`, which `archive` regenerates. `roadmap/` (registry and `archive/`) and the planning tops were already covered. Directories the batch created (`roadmap/archive/...`) are removed once they are empty. `_scratch_root` copies the same set, so a dry-run `archive` cannot write through a symlink into the live `roadmap.md`. `archive`'s `cmd_archive` returns an exit code and raises `ValueError`, so `_run_changes` handles a return code, `SystemExit` and `ValueError`.
- **A3, dry-run id map.** `id_map_lines(before, after)` composes the pre-batch → final id by `node_key`. It prints `Display ids changed (old -> new):` and one `  old -> new` line per surviving pre-batch node whose id changed, sorted by natural id. It then prints the existing wave lines. Created and removed nodes are omitted.
- **A4, tests and docs.** See `## Probes

- add-node `colour: false` / `null` / `[]`: refused before any entry runs (tests).
- edit-node `colour: false`: refused (test).
- indent `to_parent: false`: refused, because indent takes no `--to-parent` (test).
- move-node `index: 0` and `renumber_outline: false`: refused, because they are options of the parser but not restructure fields.
- archive `deep: false` (test) and `force: false`: refused.
- remove-node `dry_run: true`: refused, so an entry cannot silently turn into a rehearsal.
- add-node `repo_root` and `help: false`: refused, because `--repo-root` belongs to the top-level crud parser and `--help` is excluded.
- add-dependency with `set:`: refused. group-nodes with `node:`: refused.
- add-node `dependencies: []` (alias field), edit-node `sync_codename: true`, move-node `to_parent: null` + `id`: accepted, as intended.
- edit-node `set:` keys: these are values of `--set`, not entry fields. As on the CLI, edit-node checks them against `EDIT_WHITELIST` when it runs, and a bad one refuses the batch and restores everything. Left as is.
- Each malformed case runs after a valid lead entry, and the test asserts the tree is unchanged, so the refusal happens before earlier entries run.

## Added`. `docs/roadmap-authoring.md` § Batch edits describes the new ops, their fields, the single validation, the restore set and the id map. It gives one inline YAML entry per new op. The file is at the 400-line cap, so the examples stay inside the existing paragraph. The `apply` help in `roadmap_crud_argparse.py` names the new ops and the id map.

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

- `python -m pytest -q -n 4` → 5415 passed (round 0). Fix round 1: targeted apply, remove-node, move-node and outline-group tests pass.
- `python specy_road/bundled_scripts/validate_file_limits.py` → OK.
- `ruff check specy_road tests` → clean.
- Red-green: with the deferral disabled, `test_a_regroup_applies_in_one_run_with_one_validation` fails with `assert 9 == 1`.

## Probes

- add-node `colour: false` / `null` / `[]`: refused before any entry runs (tests).
- edit-node `colour: false`: refused (test).
- indent `to_parent: false`: refused, because indent takes no `--to-parent` (test).
- move-node `index: 0` and `renumber_outline: false`: refused, because they are options of the parser but not restructure fields.
- archive `deep: false` (test) and `force: false`: refused.
- remove-node `dry_run: true`: refused, so an entry cannot silently turn into a rehearsal.
- add-node `repo_root` and `help: false`: refused, because `--repo-root` belongs to the top-level crud parser and `--help` is excluded.
- add-dependency with `set:`: refused. group-nodes with `node:`: refused.
- add-node `dependencies: []` (alias field), edit-node `sync_codename: true`, move-node `to_parent: null` + `id`: accepted, as intended.
- edit-node `set:` keys: these are values of `--set`, not entry fields. As on the CLI, edit-node checks them against `EDIT_WHITELIST` when it runs, and a bad one refuses the batch and restores everything. Left as is.
- Each malformed case runs after a valid lead entry, and the test asserts the tree is unchanged, so the refusal happens before earlier entries run.

## Added

- `roadmap_crud_ops.deferred_validation` + `_VALIDATION_DEFERRED` + the early return in `run_validate_raise`: the in-process switch that defers per-command validation (A2).
- `roadmap_apply_entries.py` (new module): split out for the file-limits cap; holds the entry → argv → parser path.
- `RESTRUCTURE_FIELDS`: the fields the new ops may use (A1).
- `_command`: each op's parser, its subcommand prefix and its own long options (A1; fix round 1).
- `_POSITIONALS` + `_positional_argv`: one table for each op's positional fields, replacing the per-family argv builders (fix round 1).
- `_parse_entry` field-name rule: every field is checked against the command's options before its value is converted, and `apply_op` is recorded for error messages (A1; fix round 1).
- `--to-parent` in `_option_argv`'s null branch: `to_parent: null` means the root, as `parent_id: null` does.
- `id_map_lines`: the composed dry-run `old -> new` map (A3).
- `_run_changes` return-code and `ValueError` branches: `archive`'s handler returns an exit code and raises `ValueError` instead of exiting.
- `_run_changes` final `run_validate_raise` call: the one validation per batch (A2).
- `_batch_paths`: adds `roadmap.md` / `roadmap-context.md` to the snapshot and the scratch copy (A2).
- `_dirs_under` + empty-directory pruning in `_restore`: a rolled-back first archive leaves no empty `roadmap/archive/` behind.
- Test `test_dry_run_prints_the_composed_id_map_before_the_waves`: A3 map composed across group/move/indent/outdent/remove, with created nodes omitted, printed before the waves, nothing written.
- Test `test_a_regroup_applies_in_one_run_with_one_validation`: A4 regroup in one run. It wraps the public `roadmap_crud_ops.validate_at` with a counter because "one validation" is the acceptance criterion itself.
- Test `test_a_refused_entry_after_an_archive_restores_everything`: A4 archive followed by a refusing entry restores every file, generated files included.
- Parametrized cases in `test_a_malformed_entry_is_refused_before_anything_runs`: add-node `colour` set to false, null and [], edit-node `colour: false`, move-node `index`, indent `to_parent: false`, group-nodes without `nodes`, archive `deep: false`. They cover unknown fields and fields the command does not take, refused before a valid earlier entry runs (A1; fix round 1).
- Mocks: none besides the `validate_at` counter above.
