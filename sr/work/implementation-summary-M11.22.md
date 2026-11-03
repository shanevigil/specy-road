# Implementation summary: M11.22 — Worker worktrees can include nested sibling repositories

Branch `feature/rm-nested-repo-worktrees`, base `a349f83d`.

## What changed

**A1 — config, pickup, delegate.** `roadmap/git-workflow.yaml` takes an optional `nested_repos` list. Each entry is either a project-relative path or `{path, integration_branch, remote}`, and the last two default to the file's own values. The schema refuses absolute paths and `.`/`..` segments. The logic lives in a new module, `specy_road/nested_repos.py`. `add_nested_worktrees` creates a worktree of each repository at the same path inside the leaf's worktree:

- A repository the leaf's touch zones cover (`covers`: the zone names it or something inside it, from either root) gets the leaf's branch. The branch is created at the repository's integration tip (remote-tracking ref first, nothing fetched), or checked out if it already exists.
- Any other repository gets `--detach` at that tip.
- A worktree already present is left alone.

Call sites:

- `do_next_task._finalize_pickup` (`--worktree` only) calls it through `announce_nested_worktrees`. A failure there is a warning, because the claim is already pushed.
- `worker_ops_launch._launch_locked` calls it only when the tree is the leaf's own worktree, not the coordinator checkout. A failure there is a `WorkerError`.
- Delegate's uncommitted-work check no longer counts a nested repository's directory (`?? src/engine/`) as dirt.

**A2 — reconcile, finish, docs.**

- **Reconcile.** `worker_reconcile._reconcile_locked` diffs each nested repository in the worker's tree from its merge base with its integration branch, committed or not, through `nested_changes`. The results go in a new delta key, `nested_changed`, and into the same `outside_touch_zones` judgement as the main repo, so an edit in a detached repository sets `needs_reconcile`. Untracked files in nested repositories join `untracked`, and the nested directory itself is dropped from the main repo's untracked list. `reconcile_lines` and the event summary report the nested count.
- **Merge landing.** `land_merge_feature_into_integration` calls `land_nested_branches` after its preflight checks and before the land check or main merge. For each nested repository holding the feature branch, it fetches, skips the repository if the branch is already in `<remote>/<ib>`, then merges `--no-ff` in a detached temporary worktree and pushes `HEAD:refs/heads/<ib>`. No checkout of the nested repository moves. The first failure returns before the main repository moves; a re-run skips repositories already landed.
- **Implementation gate.** `finish_implementation_check.implementation_paths` adds in-zone changes made in nested repositories (`nested_zone_paths`), so a leaf whose work is only nested can finish.
- **Docs.** `docs/git-workflow.md` gains a field paragraph and a "Nested repositories (`nested_repos`)" section covering layout, reconcile, finish, review-packet, and worktree pruning.

**A3 — review-packet.** The new `specy_road/bundled_scripts/review_packet_nested.py` renders a `## Nested repositories` section after `## Diff`. For each configured repository it lists the changed paths (project-relative, with outside-zone marks judged as the main repo's are) and the diff `<merge base>...<leaf branch>`, using the local branch first and the remote-tracking one second. A diff past `--max-diff-lines` goes to `work/reviews/<id>/DIFF-nested-<path>.patch` instead. The section is absent when `nested_repos` is not configured. `review_packet.py` was at its 400-line cap. It gained one import line, and the existing two-line `_diff(...)` entry became one line, so the file stays at 400.

## Touch zones (final list)

The originals plus these, added on this branch with `specy-road edit-node M11.22 --add touch_zones=…` (commit `0bdea0cf`), as the maintainer's note on the planning sheet allows:

- `specy_road/nested_repos.py` — new module; the logic would push `git_workflow_config.py` (395 lines) and `review_packet.py` (400) over the file cap.
- `specy_road/bundled_scripts/review_packet_nested.py` — new module for the packet section, for the same cap.
- `specy_road/worker_ops_launch.py` — delegate creates the leaf worktree and checks it for dirt here, not in `worker_ops.py` (a re-export facade).
- `specy_road/bundled_scripts/do_next_task.py` — pickup `--worktree` creates the leaf worktree here.
- `specy_road/finish_implementation_check.py` — without it, the finish gate refuses a leaf whose only in-zone work is in a nested repository.

`specy_road/git_workflow_config.py` and `specy_road/worker_ops.py` are unchanged. The config reader lives in `nested_repos.py` beside its users, and delegate's code is in `worker_ops_launch.py`.

## Not covered (deliberately out of scope)

- `pr` mode does not push nested branches or open PRs there; the docs say to do it by hand.
- `land_check_cmd` runs on the main repository's merge commit only. Its temporary worktree has no nested repositories.
- Removing a leaf worktree leaves the nested worktree registrations behind. The docs name `git -C <repo> worktree prune`; `doctor` does not prune them.
- `sr/schemas/git-workflow.schema.json` is a copy for the toolkit's own `sr/` roadmap, outside the zones, and was not updated. `specy_road/templates/project/roadmap/git-workflow.yaml`, the commented template, has no `nested_repos` example, for the same reason.

## Verification

- `pytest -n auto`: 3591 passed, 2 skipped.
- `ruff check specy_road tests`: clean.
- `specy-road file-limits`: OK.
- `specy-road validate` and `specy-road export --check` (the `sr/` project): OK.
- New tests: `tests/test_nested_repo_worktrees.py` and `tests/test_nested_repo_finish.py`, 23 tests.

## Added

- `specy_road/nested_repos.py` — new module: `nested_repos` config handling and its callers, kept out of files at the cap.
- `NestedRepo` dataclass — one configured repository with its defaults resolved.
- `NestedRepoError` — lets pickup warn and delegate refuse when a repository's worktree cannot be made.
- `nested_repos()` — reads the config; empty when it is absent or invalid, so projects without it behave as before.
- `is_repo_top()` guard — makes sure a configured path is its own repository and not a directory of the main one.
- `covers()` — decides branch versus detached from the touch zones, in either root's form.
- `nested_prefixes()` / `in_nested()` — keep a nested directory out of delegate's dirty check and reconcile's untracked list.
- `_has_branch()` — adopts an existing leaf branch instead of failing `worktree add -b`.
- `add_nested_worktrees()` — A1: the worktrees themselves; idempotent.
- `announce_nested_worktrees()` — pickup's wrapper; a warning, not an exit, after the claim is pushed.
- `_merge_base()` / `nested_changes()` — A2: reconcile's diff and untracked files per nested repository.
- `branch_tip()` / `branch_diff_range()` — the leaf branch's range in a nested repository, shared by the gate and the packet.
- `nested_zone_paths()` — A2: lets finish's implementation gate see nested work.
- `_land_one()` / `land_nested_branches()` — A2: merge and push nested branches first, idempotent on re-run.
- Branch in `land_merge_feature_into_integration` — returns the nested failure before the main repository moves.
- Branch in `_launch_locked` — nested worktrees only in the leaf's own worktree (the coordinator checkout's repositories are the originals); `in_nested` exemption in the dirty check.
- Branch in `_reconcile_locked` — `nested_changed` delta key, nested paths in the outside-zone judgement, nested directory dropped from untracked; `reconcile_lines` prints the nested count, guarded with `.get` for events recorded before this change.
- Lazy import in `implementation_paths` — `nested_repos` imports `finish_implementation_check`.
- `specy_road/bundled_scripts/review_packet_nested.py` (`nested_diff_section`, `_repo_lines`, `_patch_name`) — A3: the packet section; lazily imports `review_packet._fence` (circular otherwise).
- Schema: `nested_repos` property and `$defs/nestedRepoPath` — the config shape and path safety.
- Tests: `add_nested_repo` fixture helper — one nested repository with its own bare origin, ignored and configured.
- Tests: schema acceptance and refusals; defaults per entry; `covers` table.
- Tests: pickup `--worktree` creates the nested worktree on the branch and detached.
- Tests: delegate adds the nested worktree, a re-run is a no-op, and a non-repository path is refused.
- Tests: reconcile reports nested changes and untracked files, and flags a detached edit.
- Tests: merge landing does nested then main, re-run skip, a conflict stops before main, and a repository without the branch is left alone.
- Tests: the gate counts nested work.
- Tests: the packet section with and without outside marks, the capped diff, and no section without config.
- Mocks: none.
