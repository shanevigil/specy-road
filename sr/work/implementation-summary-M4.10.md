# Implementation summary for M4.10

## Summary

Merged feature branches can now be cleaned up in two ways.

- **A1:** `finish-this-task --delete-branch` runs only after a merge lands: `on_complete: merge`, or `auto` when its merge succeeds. It then deletes the feature branch locally and on the remote, printing one line for each delete. A checked-out branch cannot be deleted, so finish first moves this checkout to the integration branch. In the `worker delegate` layout another worktree holds the integration branch, so this checkout detaches at it instead, and the output says which happened. finish tries the remote delete only when a remote-tracking ref for the branch exists, so a branch that was never pushed gets no remote delete and no warning. A failed delete prints a warning, and finish still exits 0 because the work has already landed. Under `pr`, `--delete-branch` is refused with exit 1 before the bookkeeping commit, because until the PR merges the branch is the only copy of the work.
- **A2:** `specy-road branches prune [--delete] [--base] [--remote] [--repo-root]` first runs `git fetch --prune <remote>`. It then lists the `feature/rm-*` branches, local and remote, that `<remote>/<integration>` contains. Two kinds of contained branch are skipped:
  - a branch with a registry row, in the working-tree registry or in the integration ref's registry, because a fresh pickup's tip *is* an integration commit;
  - an open milestone rollup branch (`milestone_execution.rollup_branch` whose state is not `closed`), because a fresh rollup is contained in the integration branch too.

  Without `--delete` nothing changes. With it, each branch is deleted and reported; if any delete fails the command exits 1. If the fetch fails it exits 1 before listing anything, because a stale remote-tracking ref could delete work pushed since.
- **A3:** `docs/git-workflow.md` has a new section, "Deleting merged feature branches", linked from the quickstart and from step 3 of "Merge back". The `specyrd-finish` skill describes `--delete-branch` (as step 8) and `branches prune`.

Both commands reuse the merged-into check from `grind_session_cleanup.py`, as the planning sheet asked. Its helpers are now public. The old `_delete_one` is split into `delete_local_branch` and `delete_remote_branch`, so prune can delete a local-only or a remote-only branch. `delete_merged_branch` composes the two exactly as `_delete_one` did, so grind-session behaviour is unchanged: the existing grind cleanup tests pass unedited.

`finish_task.py` was at the 400-line file cap, and `_parse_args` was within a few lines of the 80-line function cap. The parser therefore moved, unchanged apart from the new flag, into `specy_road/bundled_scripts/finish_task_args.py`.

## Changes

- `specy_road/bundled_scripts/grind_session_cleanup.py`: public `merged_into`, `delete_local_branch`, `delete_remote_branch` and `delete_merged_branch` (the old `_delete_one`).
- `specy_road/bundled_scripts/finish_task_args.py` (new): finish's argument parser, plus `--delete-branch`.
- `specy_road/bundled_scripts/finish_task.py`: uses `parse_finish_args`; calls `delete_branch_preflight` right after the mode is resolved.
- `specy_road/finish_modes.py`: `delete_branch_preflight` and `delete_landed_branch`; `apply_on_complete_mode` calls the latter after a successful landing.
- `specy_road/bundled_scripts/branches_cli.py` (new): `branches prune`.
- `specy_road/cli.py`: `branches` added to `_FORWARDED`.
- `specy_road/cli_usage.py`: help lines for `--delete-branch` and `branches prune`.
- `docs/git-workflow.md` and `specy_road/templates/specyrd/commands/specyrd-finish.md`: the A3 docs.
- `tests/test_branch_cleanup.py` (new); `tests/test_cli.py` (finish `--help` now also asserts `--delete-branch`).

The touch zones in the brief are accurate; every changed path is inside them.

## Verification

- `pytest`: 2258 passed, 2 skipped on the first implementation commit. After the two added tests: `tests/test_branch_cleanup.py` 8 passed. The doc-link, refresh-stubs, specyrd-init, CLI, grind cleanup, prerelease s2 and s5 tests: 95 passed.
- `specy-road file-limits`: OK.
- `specy-road validate --repo-root tests/fixtures/specy_road_dogfood`: OK.
- `specy-road export --check --repo-root tests/fixtures/specy_road_dogfood`: OK.

## Notes for reviewers

- **Known gap, re-run after a failed landing:** when a merge landing fails, `finish-this-task` is re-run to retry it (`retry_merge_landing`, reached from `feature_rm_registry.report_finish_already_done_on_branch`). That path does not see `--delete-branch` and does not delete the branch. Covering it would mean threading the flag through `feature_rm_registry.py`, which is outside the touch zones. On that path the branch can be deleted afterwards with `branches prune --delete`.
- **Known gap, milestone rollup:** on the milestone rollup path (`try_milestone_rollup_finish`), the leaf merges into the rollup branch rather than the integration branch, and `--delete-branch` is not applied. Nothing is printed about it.
- **Local deletes in prune:** prune uses `git branch -d`, the same as grind. git also requires `HEAD`, or the branch's upstream, to contain the branch, so the docs and `--help` say to run prune from the up-to-date integration branch. A refusal is reported per branch, and the command exits 1.
- **Shared file:** `specy_road/cli.py` is also in a live session on `feature/rm-stale-command-check`. My change there is one added line in `_FORWARDED`.

## Added

- `grind_session_cleanup.merged_into`: the existing `_merged_into`, made public so finish and prune reuse it.
- `grind_session_cleanup.delete_local_branch`: split out of `_delete_one`, so prune can delete a branch that exists only locally.
- `grind_session_cleanup.delete_remote_branch`: split out of `_delete_one`, so prune can delete a branch that exists only on the remote.
- `grind_session_cleanup.delete_merged_branch`: `_delete_one` renamed and made public, composing the two above. It is used by grind and finish.
- `finish_task_args.parse_finish_args` and `_add_landing_args`: finish's parser moved out to stay under the 400-line file cap and the 80-line function cap.
- `--delete-branch` flag: A1.
- `finish_modes.delete_branch_preflight`: guard that refuses `--delete-branch` under `pr` before bookkeeping. Reached by `test_finish_delete_branch_is_refused_under_pr_before_any_bookkeeping`.
- `finish_modes.delete_landed_branch`: the A1 deletion.
- Branch in `delete_landed_branch` between `checkout --detach` and `checkout`: needed when another worktree holds the integration branch. Reached by the `delegate-worktree` case.
- Branch in `delete_landed_branch` that skips the remote delete when there is no remote-tracking ref: needed for a branch that was never pushed. Reached by the `never-pushed` case.
- Call to `delete_landed_branch` in `apply_on_complete_mode`: runs only after a successful landing.
- `branches_cli` (`_branches`, `_live_branches`, `_merged`, `_delete`, `_say`, `cmd_prune`, `build_parser`, `main`): A2.
- Guard in `_live_branches` for claimed branches and open rollups: these look merged but are still in use. Reached by `test_prune_lists_merged_unclaimed_branches_and_deletes_nothing` and `test_prune_delete_removes_only_the_listed_branches`.
- Guard in `cmd_prune` for a failed fetch (exit 1): a stale remote-tracking ref could delete newer work. Reached by `test_prune_refuses_without_a_fresh_fetch`.
- Branch in `cmd_prune` that prints "Nothing to prune": reached by the second run in `test_prune_delete_removes_only_the_listed_branches`.
- Branch in `_say`/`_delete` for a failed delete (exit 1): reached by `test_prune_delete_reports_a_refused_delete_and_exits_1`.
- `branches` entry in `cli._FORWARDED`: dispatch. Reached through `cli.main` in `test_prune_lists_merged_unclaimed_branches_and_deletes_nothing`.
- Mocks: none. All tests use real git repos with a bare origin.
- Tests in `tests/test_branch_cleanup.py`:
  - `test_finish_delete_branch_deletes_it_locally_and_on_the_remote`, with cases `same-checkout`, `delegate-worktree` and `never-pushed` (A1);
  - `test_finish_delete_branch_is_refused_under_pr_before_any_bookkeeping` (A1 guard);
  - `test_prune_lists_merged_unclaimed_branches_and_deletes_nothing` (A2 report and CLI wiring);
  - `test_prune_delete_removes_only_the_listed_branches` (A2 `--delete`);
  - `test_prune_delete_reports_a_refused_delete_and_exits_1`;
  - `test_prune_refuses_without_a_fresh_fetch`.
- Assertion in `tests/test_cli.py::test_specy_road_finish_this_task_help`: `--delete-branch` appears in `--help`.
