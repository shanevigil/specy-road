# Implementation summary — M22.14 deps-ids-briefs-and-landed-branch

## What changed

- `specy_road/bundled_scripts/roadmap_crud_ops.py`: `edit_node_set_pairs` runs each `dependencies` value through `resolve_dependency_refs` before `apply_set`. A node_key is kept, a display id becomes its key, and the stored value is still node_keys. An empty value is left empty, so a clear still removes the field. An unknown token raises the existing `dependency 'X' is neither a node id nor a node_key in the roadmap` before the field is applied. Archived keys, de-duplication, self and cycle refusals and the all-or-nothing write are the same path as before. This is the path `set-dependencies`, `edit-node --set` and `PATCH /api/nodes/{id}` share.
- `specy_road/bundled_scripts/roadmap_crud_argparse.py` and `specy_road/cli_usage.py`: the `set-dependencies` help says KEY or ID.
- `specy_road/finish_work_artifacts.py`: `remove_main_checkout_pickup_files` removes the main checkout's `brief-<ID>.md` and `prompt-<ID>.md` when this checkout is a linked worktree. The path is the project's `work/` via `project_prefix` (`sr/work/` in a nested layout). Each file must be a regular file that `git ls-files` shows as untracked. A symlink anywhere on that path, a symlinked `work/` directory, a tracked copy, and a file whose tracking git cannot establish are left alone. Each removal is printed as `[ok] removed <path>`. `remove_work_file` is not used, because it follows symlinks.
- `specy_road/bundled_scripts/abort_task_pickup.py`: `_remove_pickup_work_files` calls that helper after its own `work/` cleanup.
- `specy_road/bundled_scripts/finish_task.py`: the same helper runs after a finish returns (a merge or auto landing, a pr tail, or a milestone rollup), and only when work-artifact cleanup is on. That decision is read once, on the feature branch, before any landing can move the checkout. A refused landing raises before the removal, so the main checkout's copies stay. After a merge or auto landing that did not pass `--delete-branch`, and only when this checkout is still on the feature branch, finish ends with `[ok] this checkout is still on <feature> (landed into <ib>); next: git switch <ib>`. A pr finish removes the files and does not print that line.
- `specy_road/finish_modes.py`: `retry_merge_landing` reads the leaf's node id and the cleanup flag right after `refuse_unless_finish_tip`, before the landing or `--delete-branch` can move this checkout. Both results (newly landed, already merged) then go through `close_merged_checkout`, which takes that `cleanup` decision.
- `specy_road/finish_milestone_rollout.py`: `retry_milestone_rollup_landing` reads the yaml cleanup flag before `land_milestone_rollup` (which ends on the integration branch) and removes the main checkout's copies after it returns. A failed landing raises inside `land_milestone_rollup` before that removal.
- `docs/git-workflow.md`: one sentence on the `merge` entry says that.
- `CHANGELOG.md`: three [Unreleased] Fixed entries.

`specy_road/bundled_scripts/roadmap_edit_fields.py` is unchanged. `_parse_dependency_keys` still receives node_keys.

## Touch zones (final)

`specy_road/bundled_scripts/roadmap_edit_fields.py`, `specy_road/bundled_scripts/roadmap_crud_argparse.py`, `specy_road/cli_usage.py`, `tests/test_roadmap_crud_dependencies.py`, `specy_road/finish_work_artifacts.py`, `specy_road/bundled_scripts/abort_task_pickup.py`, `tests/test_finish_work_cleanup.py`, `tests/test_abort_task_pickup.py`, `specy_road/bundled_scripts/finish_task.py`, `tests/test_finish_merge_mode.py`, `docs/git-workflow.md`, `CHANGELOG.md`, `specy_road/bundled_scripts/roadmap_crud_ops.py`, `tests/test_gui_app_routes_nodes_errors.py`, `tests/test_finish_merge_failure_undo.py`, `specy_road/finish_modes.py`, `specy_road/finish_milestone_rollout.py`.

`tests/test_finish_merge_failure_undo.py`, `specy_road/finish_modes.py` and `specy_road/finish_milestone_rollout.py` were each added with `specy-road edit-node` before that file was edited. Adding the rollout file pushed `M22.json` over the chunk limit, so the router moved `M22.14` into `roadmap/phases/M22__b303b5.json`. The same command rewrote the claim's `touch_zones` in `roadmap/registry.yaml` so the row matches the node. `roadmap_edit_fields.py` stayed in the list because the brief names it and the dependency parser there is what the resolved keys still go through. `docs/roadmap-authoring.md` and `docs/pm-workflow.md` still describe `set-dependencies` as taking node_keys; the sheet leaves `docs/roadmap-authoring.md` to M22.11, and neither file is in this leaf's zones.

A6 is not binding: `M16.1.1` and `M16.1.2` are Not Started. No file under `tests/parity/` changed.

## Fix round

The checkout guidance is printed after the landing outcome whenever this checkout is still on the feature branch. Three tests in `tests/test_finish_merge_failure_undo.py` still required the outcome to be the final line on that path: a merge with no `--delete-branch`, and a landing whose post-checkout hook fails after HEAD is already the feature branch (`land: local` and push). Each still asserts its outcome line, and the final line is the guidance. `--delete-branch`, the retried landing, and the already-merged follow-up still end on their outcome lines. The second `_git` in `tests/test_abort_task_pickup.py` was removed; those tests use the helper already at the top of the file.

## Fix round 2 (gpt-5.6-sol-high at `3d10a8a1`)

`retry_merge_landing` looked the node up with `finish_already_done_on_branch` after `report_landed`. With `--delete-branch` and a stale local `dev`, `report_landed` first moved this checkout to a detached stale `dev` (and `git branch -d` refused, so the branch stayed). The stale checkout still holds the registry row, so the lookup returned `None` and the retry raised `TypeError` before the main-checkout cleanup. The node id is now read right after `refuse_unless_finish_tip`, while this checkout is still on the branch. The single caller, `report_finish_already_done_on_branch`, has just made the same lookup and got a node. The test extension failed with that `TypeError` at `3d10a8a1` and passes now.

The same class ("leaf or project state read from the working tree after a landing or `--delete-branch` moved it") also reached the work-artifact cleanup flag. `drop_main_checkout_pickup_files` read `git-workflow.yaml` after the landing: from a stale detached `dev` on this retry, and from the integration branch after either rollup landing. Each path now reads the flag on the feature branch before the landing and passes the result on, and `drop_main_checkout_pickup_files` is gone. With the flag read late again, the extended test fails: the stale `dev` config turns cleanup off, so the main copies stay.

## Probes

- Class "a successful merge whose stdout must end on the landing outcome": re-ran `tests/test_finish_merge_failure_undo.py` before the edit; the only failures were `test_a_landed_finish_prints_its_outcome_last` with no `--delete-branch`, and `test_feature_checkout_failure_keeps_a_landed_finish` for `local` and `push`. Each stdout already ended with the checkout guidance. The `--delete-branch` rows, the retried landing, and the already-merged follow-up still ended on their outcome lines, so those assertions stayed.
- Other finish tests that name a landing outcome (`tests/test_finish_merge_mode.py`, `tests/test_finish_work_cleanup.py`, `tests/test_prerelease_s2.py`, `tests/test_prerelease_s5.py`, `tests/test_finish_on_complete_override.py`, `tests/test_finish_pr_mode_merge.py`, `tests/test_branch_cleanup.py`): they use `in`, or they already require the guidance as the final line (`endswith`). No other `_last_line` or `endswith` requires the outcome to be last.
- `test_restore_failure_after_reset_saves_a_copy` asserts `still on` is absent from the undo error of a failed landing. That test passed, so the guidance is not on that path.
- Class "a later function definition shadows an earlier helper in the same module": the only doubled name this leaf added is `_git` in `tests/test_abort_task_pickup.py`. `tests/test_finish_work_cleanup.py` and `tests/test_finish_merge_mode.py` each define `_git` once, in their own module. The later abort definition was deleted. Its callers do not read command output, so the earlier `cwd=` helper covers them.
- `specy-road digest --check` fails on the quality-by-area table. Rendering the digest at the merge commit and again with this zone edit produced the same text, so the drift was already on the merged branch and this edit does not change `roadmap-context.md`.
- Class "a successful merge retry exits before the shared post-success tail": `retry_merge_landing` had two `SystemExit(0)` paths, one for already merged and one for a new landing, and neither reached the removal or the checkout line. Both results now fall through to one `close_merged_checkout` call, the same function the first finish uses after `apply_on_complete_mode`. A refused landing still raises inside `merge_landing_failed` before that call.
- Other success exits: a first milestone rollup only removes the files (no merge guidance) after `try_milestone_rollup_finish` returns. The pr tail reaches `close_merged_checkout` and removes the files; the line stays off because the mode is not merge or auto.
- `--delete-branch` on a retry: `close_merged_checkout` skips the line. `test_a_retried_landing_prints_its_outcome_last` still requires the already-merged outcome to be the final line in that case.
- A non-linked retry ends on the feature branch too. `test_a_retried_landing_prints_its_outcome_last` keeps the new landing's outcome and now requires the checkout guidance as the final line. Its `--delete-branch` follow-up still ends on the already-merged outcome.
- `report_landed` no longer says it runs every post-landing step or that the outcome is always the last line. Session cleanup and `--delete-branch` still print before the outcome.
- Class "a finish that returns leaves the main checkout's untracked brief and prompt": `close_merged_checkout` returned before the removal unless the mode was merge or auto, so a pr finish left the files. The removal now runs for every return into that function, and the checkout line stays behind the merge-or-auto, `--delete-branch`, and current-branch checks. A refused merge still raises inside `merge_landing_failed` before that call. `abort-task-pickup` still removes the files on its own path.
- The same class on the rollup retry: `retry_milestone_rollup_landing` returned True after `land_milestone_rollup` without the removal, and `report_finish_already_done_on_branch` then raised `SystemExit(0)`. The retry now removes the files immediately after `land_milestone_rollup` returns. A failed step inside `land_milestone_rollup` raises before that, so the first failed rollup still keeps the copies. The first rollup path in `finish_task` removes them the same way after `try_milestone_rollup_finish` returns True.
- A repeat pr finish that finds the node already complete exits in `feature_rm_registry.py` before `close_merged_checkout`. That file is outside the zones. The first pr finish is the return that removes the files. `--delete-branch` on a merge still removes the copies: the branch check that skips the checkout line is after the removal.
- Class "state read after a landing or `--delete-branch` moved the checkout" (fix round 2), every reader after a landing in this change:
  - `retry_merge_landing` node id: read after `report_landed`, so a stale detached `dev` gave `None` and a `TypeError`. Now read before the landing. Fixed; tested.
  - `retry_merge_landing` cleanup flag: read late from the moved checkout. Now read before the landing. Fixed; tested (the stale `dev` config turns cleanup off).
  - `retry_merge_landing` after a feature checkout that fails once the landing succeeded (M22.10's warning path): the checkout can sit on `ib`. Both values are now read before `land_on_integration`, so this path is covered by the same change.
  - `retry_milestone_rollup_landing`: the node id is a parameter from the caller's earlier lookup. The cleanup flag was read after `land_milestone_rollup`, which ends on the integration branch. Now read before the landing. Fixed; the rollup retry test still passes.
  - First finish, rollup return: `try_milestone_rollup_finish` ends on `ib` before the removal. The flag was read there. It is now read in `_finish_locked` before `try_milestone_rollup_finish`. Fixed.
  - First finish, merge or auto with `--delete-branch`: `apply_on_complete_mode` leaves the checkout on `ib`. The flag was read there. It is now the same pre-landing value. Fixed. `node_id` was already read before the landing.
  - `close_merged_checkout`'s `current_branch(repo)` is read after the landing on purpose: the guidance line is about where this checkout ended up.
  - `remove_main_checkout_pickup_files` uses `project_prefix` (`git rev-parse --show-prefix`) and `--git-common-dir`. Neither depends on the checked-out branch. No change.
  - `abort-task-pickup`: `node_id` comes from its arguments, and it reads no cleanup flag for the main-checkout copies. No change.
  - The single caller of `retry_merge_landing`, `report_finish_already_done_on_branch`, has just received a node from the same `finish_already_done_on_branch` call. The only step in between is a print, so the early lookup cannot return `None`.

## Added

### Helpers

- `_dependency_set_as_keys`: split a dependencies value and map each token through `resolve_dependency_refs` before the field is applied.
- `_main_git_root`: the main checkout's git root when the current project root is a linked worktree.
- `_symlink_on_path`: whether any component of the brief or prompt path is a symlink, or whether that cannot be established.
- `remove_main_checkout_pickup_files`: the one removal finish and abort share for the main checkout's untracked brief and prompt.
- `close_merged_checkout`: that removal after finish returns, when the `cleanup` decision read before the landing says so, then the checkout line only for a merge or auto landing that left this checkout on the feature branch without `--delete-branch`. A pr finish removes the files and does not print the line.
- `drop_main_checkout_pickup_files` was added in an earlier round and removed in fix round 2. It read the cleanup flag after the landing; each caller now reads the flag before the landing and checks the result itself.
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
- Main-checkout copies are removed when a finish returns: a merge or auto landing, a pr tail, a milestone rollup, a rollup retry after `land_milestone_rollup` returns, and a merge retry. A refused landing raises before that call, so the copies stay. The checkout line stays limited to merge and auto.
- A merge retry has no `--no-cleanup-work` argument. The yaml cleanup flag still applies. That limit is in `retry_merge_landing`'s docstring.
- `if cleanup:` before `remove_main_checkout_pickup_files` in `close_merged_checkout`, in finish_task's rollup return, and in `retry_milestone_rollup_landing`. Each `cleanup` is read on the feature branch before the landing, so a landing that moves the checkout cannot change it.

### Mocks

- `finish_task.merge_undo_snapshot` returns None for the linked-worktree retry test's first finish, so a rejected push keeps the bookkeeping commit and the next run is a retry. `test_a_retried_landing_prints_its_outcome_last` uses the same patch.

### Tests

- `test_set_dependencies_accepts_display_ids_and_refuses_an_unknown`: display id, mixed id and key, `edit-node --set`, unknown token refused with the existing sentence and the chunk unchanged, help says KEY or ID.
- `test_patch_dependencies_stores_a_display_id_and_refuses_an_unknown`: PATCH stores a display id as its node_key; an unknown token is HTTP 400 and the graph is unchanged.
- `test_linked_worktree_main_checkout_pickup_files`: embedded and nested; untracked copies removed, tracked kept, a symlink alias and its target kept, a symlinked `work/` kept.
- `test_finish_from_a_linked_worktree_removes_main_copies_after_landing`: a successful merge from a linked worktree removes the main copies and ends with the checkout line.
- `test_pr_finish_from_a_linked_worktree_keeps_main_checkout_copies`: a pr finish removes the main checkout's untracked brief and prompt and does not print the checkout line.
- `test_linked_worktree_rollup_retry_clears_main_copies`: a refused rollup push keeps the main copies; the retry that then lands removes them and does not print the checkout line. It uses the same linked-worktree layout as `test_finish_from_a_linked_worktree_removes_main_copies_after_landing`.
- `test_finish_refused_at_landing_keeps_main_checkout_copies`: a land check failure keeps the main copies and does not print the line.
- `test_linked_worktree_merge_retry_clears_main_copies_and_names_the_branch`: a linked-worktree retry that newly lands, and one that finds the branch already merged, each remove the main copies and end on the checkout line. A refused first landing keeps the copies. Extended in fix round 2 (Sol's required regression): a `--delete-branch` retry with the branch already merged on `origin` and local `dev` reset to a stale commit whose `git-workflow.yaml` sets `cleanup_work_artifacts_on_finish: false`. It exits 0, prints the already-merged outcome, leaves this checkout at the stale `dev` (asserted), removes the main copies as the branch's config says, and prints no checkout line.
- `_finish` (test): one finish call whose exit code is 0, returning its stdout.
- `test_abort_from_a_linked_worktree_cleans_the_main_checkout`: the same four file kinds from `abort-task-pickup` in both layouts.
- `test_finish_merge_prints_push_disclosure_for_unrelated_dev_commit`: extended so the successful merge ends with the checkout line.
- `test_finish_merge_omits_the_branch_line_when_the_branch_is_deleted`: the line is absent with `--delete-branch`.
