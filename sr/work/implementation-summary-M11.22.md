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

## Review round 1 (gpt-5.6-sol-medium blocked 47ca8cc6): item → change

- **R1. An existing destination is verified, not trusted.**
  - `add_nested_worktrees` checks a destination that already exists with the new `existing_worktree_problem`. The destination must be the top of a git worktree with the same `--git-common-dir` as the configured repository, and must be on the leaf's branch when the zones cover it, detached otherwise. Anything else raises `NestedRepoError` naming the problem and how to remove it.
  - Delegate turns that into a `WorkerError` (exit 1, nothing launched). Pickup prints it as a warning, because its claim is already pushed.
  - The configured repository itself is now checked before the existing-destination branch too.
  - Public-boundary regression: `test_delegate_refuses_an_ordinary_directory_where_the_nested_worktree_goes`, through `worker delegate` on the CLI with an ordinary directory at `<leaf>/src/engine`. Plus `test_an_existing_nested_worktree_in_the_wrong_state_is_refused` for the branch/detached state.
- **R2. A missing or invalid repository fails the landing.**
  - `land_nested_branches` now tells two cases apart. A configured path that is not the top of a git repository is a failure ("not the top of a git repository … restore it or drop it from nested_repos"), and `land_merge_feature_into_integration` returns it before the main checkout or merge. A valid repository without the leaf's branch is still skipped.
  - Regression: `test_a_configured_repo_that_is_gone_stops_the_landing_before_the_main_repository` asserts that `origin/dev` of the main repo is unchanged and the checkout stays on the feature branch.
- **R3. Both budgets apply to nested diffs.**
  - `build_packet` passes `max_diff_bytes` to `nested_diff_section`, and `_repo_lines` applies both budgets through `_over_budget` (`0` means no cap, as in the main diff). The "capped" line names each budget the diff exceeded.
  - `review_packet.py` stays at 400 lines: only the arguments of the existing call changed.
  - Regression: `test_review_packet_caps_a_long_single_line_nested_diff_by_bytes`, with a 5,000-byte one-line diff under `max_diff_lines=0, max_diff_bytes=100`.
- **R4. Patch names no longer collide.**
  - `patch_name` writes `/` as `+`. No path the schema accepts contains `+`, so the mapping is injective: `a/b` becomes `DIFF-nested-a+b.patch` and `a-b` becomes `DIFF-nested-a-b.patch`.
  - `nested_repos()` also normalises empty segments (`x//y/` → `x/y`), so one directory has one name.
  - Regressions: `test_capped_nested_diffs_of_paths_that_flatten_alike_keep_their_own_patch` (both repositories capped; each patch holds its own diff) and the `x//y` case in `test_entries_default_to_the_main_repositorys_branch_and_remote`. The existing cap test now expects `DIFF-nested-src+engine.patch`.
- **T1. Fixtures are promoted, not imported privately.**
  - `_project`, `_run` and `_pickup` (with `SHEET` and `FEATURE`) moved verbatim from `tests/test_baseline_gate_cli.py` into the new `tests/pickup_repo_helpers.py`, as `make_pickup_project`, `run_specy_road` and `run_pickup`.
  - `FAKE`, `worker_roster` and `_repo` moved verbatim from `tests/test_worker_cli.py` into the new `tests/worker_repo_helpers.py`, with `_repo` renamed `make_worker_repo`.
  - Each source module re-imports them under the old names, so the 25+ existing importers are unchanged and no setup is duplicated.
  - The nested tests use only public names: `make_pickup_project`, `run_pickup`, `make_worker_repo`, `run_worker_cli`, `wait_for_worker`, `ops.delegate`, `wrc.reconcile`, the CLI.
  - The `add_nested_repo` fixture now accepts a second repository (it appends to the list, and its bare origin is named with `+`) for R4.
- **Docs.** `docs/git-workflow.md` "Nested repositories" now states the R1 refusal, the R2 failure versus skip, and R3/R4 (both budgets, the `+` in patch names).

No touch zones were added in this round. The new files are under `tests/`, and the rest are already-zoned files.

- **Merge of `origin/WIP/improvements-0-3-1` (M8.2, commit d4d1097a):** one conflict, in `specy_road/worker_ops_launch.py`, resolved by keeping M8.2's `delegate(..., model: str | None, ...)` chore signature and this leaf's `_nested_dirty` helper above it. M8.2's chore path and the nested hooks in `_launch_locked` both survive; a chore's worktree gets the same nested handling as a leaf's. All three fix rounds are unchanged. `pytest -n 4` passed 36 tests in the two nested files and 606 in the 49 delegate, chore, pickup and helper modules.

## Review round 3 (gpt-5.6-sol-medium blocked 96053d7a): item → change

- **(1) Delegate in the checkout already on the claim's branch.**
  - `_launch_locked` used to set up nested repositories only for a leaf worktree. For the direct-checkout layout (`wt == git_root(repo_root)`) it now calls the new `nested_repos.align_nested_checkouts`.
  - For each configured repository in the main checkout, that function reads the required state with `existing_worktree_problem` (the same test the worktree path uses): a covered repository on the leaf's branch, an uncovered one detached at the integration tip. A repository already in that state is left alone.
  - A clean checkout (no tracked or untracked changes) is switched: `checkout <branch>`, or `-b <branch> <tip>` when the branch is missing, or `--detach <tip>`.
  - A dirty checkout in the wrong state, an unreadable status, or a switch git refuses (for example, the branch checked out in another worktree) raises `NestedRepoError`. Delegate reports it as a `WorkerError` before anything is written or launched. Each switch is printed to stderr.
  - Afterwards the round-2 R6 check covers these checkouts too: `nested_worktree_dirs` finds them under the worker's tree.
  - Regressions (`tests/test_nested_repo_finish.py`):
    - `test_delegate_in_the_checkout_on_the_claim_branch_puts_the_nested_repo_on_it_and_finish_lands_it`, through the public `worker delegate` CLI with the main checkout on `feature/rm-thing` and the nested repository on `dev`. The worker record's tree is the checkout, and the nested repository is now on the leaf's branch. A commit there (the worker's change) is then landed by finish's merge step (`land_merge_feature_into_integration`): the nested `origin/dev` carries `x = 7`, and the main `origin/dev` moves.
    - `test_direct_checkout_delegate_refuses_a_dirty_nested_repo_off_the_branch`: exit 1, nothing launched, the checkout and the file untouched.
    - `test_direct_checkout_delegate_detaches_an_uncovered_nested_repo_at_the_tip`.
- **(2) A missing integration ref is refused, never replaced by `HEAD`.**
  - The new `_source_and_tip` returns the configured repository and `base_ref(remote/branch, else local branch)`. With neither ref, it raises `NestedRepoError` ("neither <remote>/<branch> nor a local <branch> exists in <repo>; fetch it, or fix integration_branch/remote …").
  - `add_nested_worktrees` and `align_nested_checkouts` both go through it.
  - `existing_worktree_problem`'s `tip` parameter no longer defaults to `"HEAD"`.
  - Boundary test: `test_delegate_refuses_a_nested_repo_without_its_integration_branch[src/engine|lib]`. The config says `dev` and the nested repository has only `main`. Through `worker delegate`: exit 1 with that message, no worker record, and no nested worktree created, for both a covered and an uncovered repository.
- **Docs.** `docs/git-workflow.md` "Nested repositories" now states both behaviours.

No touch zones were added this round; the changes are in `nested_repos.py`, `worker_ops_launch.py`, `docs/git-workflow.md` and `tests/`, all already zoned.

## Review round 2 (gpt-5.6-sol-medium blocked e7cbab7b): item → change

- **R5. A detached destination must be at the integration tip.**
  - `add_nested_worktrees` now resolves the tip (`base_ref` of the nested repo, else `HEAD`) before it looks at the destination. It passes that tip to `existing_worktree_problem`, which for a detached destination compares the destination's `HEAD` with the tip's commit as read in the configured repository.
  - A mismatch is refused ("… is detached at <sha>, not at the integration tip <ref> (<sha>)") with the same remove-and-rerun guidance.
  - Regression: `test_a_detached_nested_worktree_off_the_integration_tip_is_refused`. The integration branch moves on, so the existing detached worktree is refused; detaching it at `origin/dev` makes it accepted again.
- **R6. Delegate checks nested worktrees for uncommitted work.**
  - `_launch_locked` adds `_nested_dirty(wt / prefix, repo_root)` to its dirty list. The new helper runs the same `status_entries` (tracked-modified and untracked, `--untracked-files=all`) in every nested repository present under the worker's tree (`nested_worktree_dirs`), and names each path git-root-relative.
  - Any entry refuses the delegation with the existing "uncommitted changes the worker could overwrite" error, before the prompt is written or anything launches. An unreadable status is refused like the main tree's.
  - This applies in the coordinator-checkout layout too, where the nested directories are the repositories themselves.
  - Public regression: `test_delegate_launches_nothing_over_a_dirty_nested_worktree[tracked|untracked]`, through `worker delegate` on the CLI. It asserts exit 1, the path named, no worker record, no prompt file, and the dirty file untouched.

- **Docs.** `docs/git-workflow.md` now says delegate checks each nested repository for tracked and untracked changes. "Detached at that tip" was already stated for R5.

No touch zones were added this round; both changes are in already-zoned files.

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

Round 3 fixes, at the commit that adds this summary:

- `pytest -n 4 tests/test_nested_repo_worktrees.py tests/test_nested_repo_finish.py`: 36 passed.
- `specy-road file-limits`: OK.
- `ruff check specy_road tests`: clean.
- The 36 modules that exercise delegate or the promoted helpers (`pytest -n 4 <those files>`): 474 passed.
- **Red-green.** Both nested test files run against 96053d7a in a temporary detached worktree (removed afterwards): 5 failed, the 3 direct-checkout tests and both missing-integration-branch cases.

Round 2 fixes, at the commit that adds this summary:

- `pytest -n 4 tests/test_nested_repo_worktrees.py tests/test_nested_repo_finish.py`: 31 passed.
- `specy-road file-limits`: OK.
- `ruff check specy_road tests`: clean.
- The 35 modules that exercise delegate or the promoted helpers (`pytest -n 4 <those files>`): 458 passed.
- **Red-green.** `tests/test_nested_repo_worktrees.py` run against e7cbab7b in a temporary detached worktree (removed afterwards): 3 failed, the R5 test and both R6 cases.

Round 1 fixes, at the commit that adds this summary:

- `pytest -n 4 tests/test_nested_repo_worktrees.py tests/test_nested_repo_finish.py`: 28 passed.
- `specy-road file-limits`: OK.
- `ruff check specy_road tests`: clean.
- The 29 modules that use the promoted helpers (`pytest -n 4 <those files>`): 364 passed.
- **Red-green.** The two new test files, run against 47ca8cc6 in a temporary detached worktree (removed afterwards), fail 7 tests: the R1 pair, R2, R3, R4, the renamed-patch cap test, and the `x//y` defaults case.
- **Full suite (`pytest -n auto`), run twice on a heavily loaded machine** (586 s and 590 s, against 205 s earlier). Each run had 1 failure, in a different worker timing test each time: `test_worker_faults.py::test_output_clears_a_stall_shorter_than_the_write_window`, then `test_worker_queue_message.py::test_message_while_running_queues_and_delivers`. Each passes when rerun outside the full suite, and neither touches nested repositories. I did not pass the full suite as a `--verify`, because neither run exited 0.

Round 0 (47ca8cc6): full suite 3591 passed; validate and export --check OK.

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
- Round 1: `existing_worktree_problem()` / `_common_dir()` — R1: an existing destination must be that repository's worktree in the required state.
- Round 1: missing-repository branch in `land_nested_branches` — R2: a configured path that is no repository fails before the main repository moves.
- Round 1: `_over_budget()` and the `max_diff_bytes` parameter of `nested_diff_section` / `_repo_lines` — R3: both packet budgets.
- Round 1: `patch_name()` (was `_patch_name`, now `+` for `/`) and empty-segment normalisation in `nested_repos()` — R4: one patch name per repository.
- Round 1: `tests/pickup_repo_helpers.py` (`make_pickup_project`, `run_specy_road`, `run_pickup`, `SHEET`, `FEATURE`) and `tests/worker_repo_helpers.py` (`make_worker_repo`, `worker_roster`, `FAKE`) — T1: promoted from the test modules, which re-import them under their old names.
- Round 2: `tip` parameter and detached-HEAD comparison in `existing_worktree_problem` — R5: a detached destination must be at the tip a new worktree would use.
- Round 2: `nested_worktree_dirs()` (nested_repos) and `_nested_dirty()` (worker_ops_launch) — R6: delegate's uncommitted-work check covers each nested repository under the worker's tree.
- Round 3: `_source_and_tip()` — (2): the configured repository and its required integration tip; no `HEAD` stand-in.
- Round 3: `align_nested_checkouts()` (nested_repos) and its call in `_launch_locked` — (1): the direct-checkout layout gets the same nested states as a leaf worktree, switching only clean checkouts.
- Round 3 tests: direct-checkout delegate then finish landing; the dirty direct checkout refused; the uncovered repository detached; the missing integration branch refused (covered and uncovered).
- Round 2 tests: the detached-off-tip refusal (and its acceptance once re-detached), and the delegate refusal over a tracked or untracked change in a nested worktree.
- Round 1 tests: the delegate public-boundary refusal of an ordinary directory, the wrong-state refusal, the gone-repository landing, the single-line byte cap, the colliding-path patches, and the `x//y` normalisation.
- Tests: schema acceptance and refusals; defaults per entry; `covers` table.
- Tests: pickup `--worktree` creates the nested worktree on the branch and detached.
- Tests: delegate adds the nested worktree, a re-run is a no-op, and a non-repository path is refused.
- Tests: reconcile reports nested changes and untracked files, and flags a detached edit.
- Tests: merge landing does nested then main, re-run skip, a conflict stops before main, and a repository without the branch is left alone.
- Tests: the gate counts nested work.
- Tests: the packet section with and without outside marks, the capped diff, and no section without config.
- Mocks: none.
