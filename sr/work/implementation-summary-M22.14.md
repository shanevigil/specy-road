# Implementation summary — M22.14 deps-ids-briefs-and-landed-branch

## What changed

- `specy_road/bundled_scripts/roadmap_crud_ops.py`: `edit_node_set_pairs` runs each `dependencies` value through `resolve_dependency_refs` before `apply_set`. A node_key is kept, a display id becomes its key, and the stored value is still node_keys. An empty value is left empty, so a clear still removes the field. An unknown token raises the existing `dependency 'X' is neither a node id nor a node_key in the roadmap` before the field is applied. Archived keys, de-duplication, self and cycle refusals and the all-or-nothing write are the same path as before. This is the path `set-dependencies`, `edit-node --set` and `PATCH /api/nodes/{id}` share.
- `specy_road/bundled_scripts/roadmap_crud_argparse.py` and `specy_road/cli_usage.py`: the `set-dependencies` help says KEY or ID.
- `specy_road/finish_work_artifacts.py`: `remove_main_checkout_pickup_files` removes the main checkout's `brief-<ID>.md` and `prompt-<ID>.md` when this checkout is a linked worktree. The path is the project's `work/` via `project_prefix` (`sr/work/` in a nested layout). Each file must be a regular file that `git ls-files` shows as untracked. A symlink anywhere on that path, a symlinked `work/` directory, a tracked copy, and a file whose tracking git cannot establish are left alone. Each removal is printed as `[ok] removed <path>`. `remove_work_file` is not used, because it follows symlinks.
- `specy_road/bundled_scripts/abort_task_pickup.py`: `_remove_pickup_work_files` calls that helper after its own `work/` cleanup.
- `specy_road/bundled_scripts/finish_task.py`: the same helper runs only after a finish succeeds (a merge or auto landing that returned, a pr tail that returned, or a milestone rollup that returned), and only when work-artifact cleanup is on. A refused landing raises before that call, so the main checkout's copies stay. After a merge or auto landing that did not pass `--delete-branch`, and only when this checkout is still on the feature branch, finish ends with `[ok] this checkout is still on <feature> (landed into <ib>); next: git switch <ib>`.
- `docs/git-workflow.md`: one sentence on the `merge` entry says that.
- `CHANGELOG.md`: three [Unreleased] Fixed entries.

`specy_road/bundled_scripts/roadmap_edit_fields.py` is unchanged. `_parse_dependency_keys` still receives node_keys.

## Touch zones (final)

`specy_road/bundled_scripts/roadmap_edit_fields.py`, `specy_road/bundled_scripts/roadmap_crud_argparse.py`, `specy_road/cli_usage.py`, `tests/test_roadmap_crud_dependencies.py`, `specy_road/finish_work_artifacts.py`, `specy_road/bundled_scripts/abort_task_pickup.py`, `tests/test_finish_work_cleanup.py`, `tests/test_abort_task_pickup.py`, `specy_road/bundled_scripts/finish_task.py`, `tests/test_finish_merge_mode.py`, `docs/git-workflow.md`, `CHANGELOG.md`, `specy_road/bundled_scripts/roadmap_crud_ops.py`, `tests/test_gui_app_routes_nodes_errors.py`, `tests/test_finish_merge_failure_undo.py`.

The last path was added with `specy-road edit-node` before that file was edited. The same command rewrote the claim's `touch_zones` in `roadmap/registry.yaml` so the row matches the node. `roadmap_edit_fields.py` stayed in the list because the brief names it and the dependency parser there is what the resolved keys still go through. `docs/roadmap-authoring.md` and `docs/pm-workflow.md` still describe `set-dependencies` as taking node_keys; the sheet leaves `docs/roadmap-authoring.md` to M22.11, and neither file is in this leaf's zones.

A6 is not binding: `M16.1.1` and `M16.1.2` are Not Started. No file under `tests/parity/` changed.

## Added

### Helpers

- `_dependency_set_as_keys`: split a dependencies value and map each token through `resolve_dependency_refs` before the field is applied.
- `_main_git_root`: the main checkout's git root when the current project root is a linked worktree.
- `_symlink_on_path`: whether any component of the brief or prompt path is a symlink, or whether that cannot be established.
- `remove_main_checkout_pickup_files`: the one removal finish and abort share for the main checkout's untracked brief and prompt.
- `_drop_main_pickup_files`: finish's call of that helper, gated on the same cleanup flag as the worktree's own session files.
- `_say_still_on_feature`: the closing line after a merge or auto landing.
- `_deps` (test): one `run_crud` call with `--repo-root`.
- `_git`, `_linked`, `_prefix` (finish cleanup tests): a linked worktree in the embedded and nested layouts.
- `_claim_leaf`, `_open_leaf`, `_place_main_copies` (abort tests): a claimed leaf whose main checkout is not on the integration branch, so abort can check that branch out in the worktree. They call the module's existing `_git`.

### Branches or guards

- An empty dependencies value is returned unchanged, so a clear still removes the field.
- A non-linked checkout does not touch another worktree's files.
- A symlink on the path, or an `OSError` while checking, leaves the file.
- A path that is not a regular file is left alone.
- `git ls-files` failing, or listing the path, leaves the file.
- The checkout line is printed only for `merge` and `auto`, not with `--delete-branch`, and only when the current branch is the feature branch.
- Main-checkout copies are removed only after finish returns from a successful landing, rollup or pr tail, so a refused landing keeps them.

### Mocks

none

### Tests

- `test_set_dependencies_accepts_display_ids_and_refuses_an_unknown`: display id, mixed id and key, `edit-node --set`, unknown token refused with the existing sentence and the chunk unchanged, help says KEY or ID.
- `test_patch_dependencies_stores_a_display_id_and_refuses_an_unknown`: PATCH stores a display id as its node_key; an unknown token is HTTP 400 and the graph is unchanged.
- `test_linked_worktree_main_checkout_pickup_files`: embedded and nested; untracked copies removed, tracked kept, a symlink alias and its target kept, a symlinked `work/` kept.
- `test_finish_from_a_linked_worktree_removes_main_copies_after_landing`: a successful merge from a linked worktree removes the main copies and ends with the checkout line.
- `test_finish_refused_at_landing_keeps_main_checkout_copies`: a land check failure keeps the main copies and does not print the line.
- `test_abort_from_a_linked_worktree_cleans_the_main_checkout`: the same four file kinds from `abort-task-pickup` in both layouts.
- `test_finish_merge_prints_push_disclosure_for_unrelated_dev_commit`: extended so the successful merge ends with the checkout line.
- `test_finish_merge_omits_the_branch_line_when_the_branch_is_deleted`: the line is absent with `--delete-branch`.

## Fix round

The checkout guidance is printed after the landing outcome whenever this checkout is still on the feature branch. Three tests in `tests/test_finish_merge_failure_undo.py` still required the outcome to be the final line on that path: a merge with no `--delete-branch`, and a landing whose post-checkout hook fails after HEAD is already the feature branch (`land: local` and push). Each still asserts its outcome line, and the final line is the guidance. `--delete-branch`, the retried landing, and the already-merged follow-up still end on their outcome lines. The second `_git` in `tests/test_abort_task_pickup.py` was removed; those tests use the helper already at the top of the file.

## Probes

- Class "a successful merge whose stdout must end on the landing outcome": re-ran `tests/test_finish_merge_failure_undo.py` before the edit; the only failures were `test_a_landed_finish_prints_its_outcome_last` with no `--delete-branch`, and `test_feature_checkout_failure_keeps_a_landed_finish` for `local` and `push`. Each stdout already ended with the checkout guidance. The `--delete-branch` rows, the retried landing, and the already-merged follow-up still ended on their outcome lines, so those assertions stayed.
- Other finish tests that name a landing outcome (`tests/test_finish_merge_mode.py`, `tests/test_finish_work_cleanup.py`, `tests/test_prerelease_s2.py`, `tests/test_prerelease_s5.py`, `tests/test_finish_on_complete_override.py`, `tests/test_finish_pr_mode_merge.py`, `tests/test_branch_cleanup.py`): they use `in`, or they already require the guidance as the final line (`endswith`). No other `_last_line` or `endswith` requires the outcome to be last.
- `test_restore_failure_after_reset_saves_a_copy` asserts `still on` is absent from the undo error of a failed landing. That test passed, so the guidance is not on that path.
- Class "a later function definition shadows an earlier helper in the same module": the only doubled name this leaf added is `_git` in `tests/test_abort_task_pickup.py`. `tests/test_finish_work_cleanup.py` and `tests/test_finish_merge_mode.py` each define `_git` once, in their own module. The later abort definition was deleted. Its callers do not read command output, so the earlier `cwd=` helper covers them.
- `specy-road digest --check` fails on the quality-by-area table. Rendering the digest at the merge commit and again with this zone edit produced the same text, so the drift was already on the merged branch and this edit does not change `roadmap-context.md`.
