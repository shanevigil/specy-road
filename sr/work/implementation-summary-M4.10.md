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

Review round 1 (Sol, at e7ba8af) is addressed on this branch.

- **Retry applies `--delete-branch`.** A re-run in merge mode enters `retry_merge_landing` and used to return without deleting. The flag now travels with the re-run's CLI args: `finish_task._resolve_context` → `resolve_feature_rm_registry_context_for_finish` → `report_finish_already_done_on_branch` → `retry_merge_landing`. After the landing (and when the branch is already on the remote), the same `delete_landed_branch` runs. The failure message names the re-run with `--delete-branch` included, so the command it prints is the one that deletes. The on-complete session file is not where this retry reads its options: that sidecar is removed in the bookkeeping commit, before the landing is attempted, and the retry already passes `session=None`. `feature_rm_registry.py` is outside the original touch zones; the review required the flag to cross that call, and there is no other caller.
- **Remote delete is leased to the checked tip.** `delete_remote_branch` (used by finish, `branches prune`, and grind's `--delete-merged-branches`) now runs `git push <remote> --force-with-lease=refs/heads/<branch>:<sha> --delete <branch>`, where `<sha>` is the remote-tracking tip that passed the merged check. A push that lands in between is rejected (`stale info`); the branch stays and the failure is reported. A branch that was never pushed is still skipped, before any lease.
- **Known gap, milestone rollup:** on the milestone rollup path (`try_milestone_rollup_finish`), the leaf merges into the rollup branch rather than the integration branch, and `--delete-branch` is not applied. Nothing is printed about it. Unchanged from round 1; the review did not ask for it.
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

### Review round 1

- `retry_merge_landing(..., delete_branch=False)`: the re-run deletes once the branch is on the remote, including when an earlier run already landed it.
- Branch in `retry_merge_landing` for an already-merged branch: deletes when the flag is set, and keeps the old "nothing to do" line when it is not. Reached by the existing re-run test without the flag, and by `test_a_retried_landing_deletes_the_branch` for the landing that had failed.
- `merge_landing_failed(..., delete_branch=False)`: the printed re-run command includes `--delete-branch` when this run passed it. Reached by the same test (the hook-rejected first run).
- `delete_branch` parameter on `report_finish_already_done_on_branch`, `resolve_feature_rm_registry_context_for_finish`, and `_resolve_context`: carries the CLI flag into the retry. The session file is not used; it is already gone.
- Lease in `delete_remote_branch`: `rev-parse` of the remote-tracking tip, then `git push --force-with-lease=refs/heads/<branch>:<sha> --delete`. A non-zero push, including a stale lease, is a failure and the branch stays. Reached by `test_a_moved_remote_tip_is_not_deleted`.
- Guard in `delete_remote_branch` when `rev-parse` fails: refuse the delete rather than lease an empty tip.
- `tests/test_grind_session.py` harness: `rev-parse` returns a sha, so the grind cleanup tests still reach the push. Reason: the lease needs the tip the mock used to leave empty.
- Assertion in `tests/test_grind_session_cleanup.py::test_with_push_it_also_deletes_the_remote_branch`: the push argv is now the leased form.
- `test_a_retried_landing_deletes_the_branch`: a rejected landing, then the same command with `--delete-branch`, deletes locally and on the remote.
- `test_a_moved_remote_tip_is_not_deleted`: the remote branch moved after the merged check; the lease refuses and the new tip is still there. finish and prune both delete through this function.
