# Implementation summary: M12.5

`specy-road worktree cleanup <ID>` and `specy-road worktree sweep [--dry-run] [--delete-local-branch]`
retire landed worktrees, moving their hand-off files to the main checkout first.

## What changed

- **`specy_road/worktree_cleanup.py` (new).**
  - Hand-off files under `work/reviews/<ID>/**` (cleanup) or `work/reviews/**` (sweep) in the worktree's own tree are moved into `reviews_root(main)` by `execute`. A file with the same bytes already there is dropped from the worktree. A different file is kept beside the existing one as `<name>.from-worktree<n>`.
  - **Plan first, act second (fix round 1, F1).** `plan_cleanup(main, wt, branch, sub)` builds a `CleanupPlan` from the untouched worktree, and nothing is moved or deleted while it does. The plan holds:
    - the prune checks from `plan_worktree`, including M14.3's foreign-repository walk, which now sees the hand-off tree before anything moves;
    - the hand-off files to move (`_salvage_list`);
    - the workers to end;
    - every refusal: prune refusals, a repository inside the hand-off tree, a hand-off dir that is or lies under a link, ignored files that are neither saved by the plan nor regenerable, a starting worker, and a human-leased worker.

    `execute(plan)` does nothing when the plan has any refusal. Otherwise it saves the hand-off files, terminates the workers, calls `remove()` and ends the session records. `cleanup_after_land` is `execute(plan_cleanup(...))`, and sweep uses the same pair. A refusal therefore moves nothing, which is a behaviour change from round 0, where hand-off files were moved even when the cleanup then refused.
  - `_salvage_list` walks with `os.walk`, which does not follow links, and skips symlinked files. It stops at any directory that holds a `.git` file, directory or link, or has a bare-repository layout, and adds a refusal for it, so the salvage step never moves a `.git` entry or anything inside a repository.
  - `sweep` (A3/A7) first runs `terminate_orphaned`, except in `--dry-run`. It then judges every linked worktree from `git worktree list` with M14.2's rules: `live_holders` plus `_live`, and `classify`/`evidence_kind`/`merged_how` for "merged with own commits". A detached `HEAD` must be contained in the integration branch. Each worktree that passes then goes through the same `plan_cleanup`/`execute` pair, and the output is one line: `removed`, `would remove`, or `kept <path>: <reason>`. Locked worktrees, the current worktree, missing directories and `TEMP_WORKTREES` (running specy-road checks) are kept. `--delete-local-branch` reuses `grind_session_cleanup.delete_local_branch` against the integration ref. Remote branches are never deleted (A5).
- **`specy_road/worktree_prune.py`.** `plan_prune` now delegates to the new `plan_worktree(main, wt, branch)`, so sweep can apply the same checks to any worktree. An empty branch (detached) skips the branch refs. Behaviour for `plan_prune` is unchanged.
- **`specy_road/bundled_scripts/worktree_cli.py`.** Adds the `cleanup` and `sweep` subcommands. On refusal, cleanup prints `error: not cleaning up <ID>:` plus one `  - <reason>` line per reason and exits 1.
- **`specy_road/session_presence.py`.** Adds `end_sessions_for(repo_root, worktree, branch)`, which ends every record (live or expired) whose worktree is inside the removed one or whose branch is the leaf's.
- **`specy_road/bundled_scripts/grind_session_cleanup.py` and `grind_session.py`** (A4).
  - `after_landing` runs after each landed leaf. It calls `cleanup_after_land` and emits a `worktree_cleanup` event.
  - When `policy.worktree_sweep == between_leaves`, it also runs `sweep` and emits a `worktree_sweep` event.
  - It is skipped in milestone-subtree mode, it ignores `PruneError` (no leaf worktree), and it never changes the exit code.
- **`specy_road/orchestration_config.py` and `orchestration.schema.json`.** Add `policy.worktree_sweep: off|between_leaves`, default `off`.
- **`specyrd-orchestrate.md`.** `worktree sweep --dry-run` is added to the session-start block, and step 7 now runs `worktree cleanup <ID>` after finish.
- **`docs/orchestration-chores.md`.** New "Cleanup" section covering both commands, the regenerable list, out-of-scope items, the `gh pr merge --delete-branch` warning (A8) and the grind-session policy.

## Touch zones

The final list is the brief's list as given. Every changed path is inside it. The new module imports from `doctor_worktrees.py`, `bundled_scripts/doctor.py` (`_complete_leaves`), `worker_orphans.py` and `worker_ops_lifecycle.py` but does not change them.

## Verification

- `pytest -q -n 4 tests/test_worktree_cleanup.py`: 18 passed (fix round 1). The 6 new foreign-repository cases fail on 146da5ba (run in a temporary detached worktree).
- Targeted suites after the fix (cleanup, prune, prune-foreign, grind-session, orchestration-config, session-plan, doctor-live, linked-worktrees-root): 273 passed. `ruff`: clean.
- Merged `origin/WIP/improvements-0-3-1` twice: the first conflict in `orchestration_config.py` was resolved by keeping both sides; the second merge was clean.
- `pytest -q -n 4` (full suite): 4412 passed in round 0; rerun by `specy-road ready` for this commit.
- `specy-road file-limits`: OK.
- `specy-road validate --repo-root tests/fixtures/specy_road_dogfood`: exit 0.
- `python scripts/check_test_private_imports.py` and `python scripts/check_clones.py`: exit 0.

## Probes

Class: the cleanup acted on the tree (moved hand-off files) before the planner had read all of it, so a repository that is not ours, or a path that is not ours, could be moved or deleted.

- Cleanup with a linked worktree of another repository, carrying an unlanded commit, under `work/reviews/M1/`: refused. Nothing moved, the foreign worktree is intact and still valid in its owner's `git worktree list` (not prunable). Covered by a test.
- Cleanup with a nested clone (`.git` directory) in the same place: refused, intact. Covered by a test.
- Cleanup with a checkout whose `.git` is a file naming its git directory (a submodule-style `--separate-git-dir`): refused, intact. Covered by a test.
- Sweep (`--dry-run` and real) with each of those three: `kept` line naming the repository; worktree and foreign repository intact. Covered by a test.
- Bare repository layout under `work/reviews/M1/` (probe script): refused by both the hand-off walk and the prune walk; nothing moved.
- `.git` directly in `work/reviews/M1/` (probe): refused; nothing moved.
- `work/reviews/M1` as a symlink to a directory outside the worktree (probe): refused, link not followed; the outside file is not moved or copied.
- A symlinked file inside `work/reviews/M1/` (probe): not salvaged, so it refuses as a non-regenerable ignored file; nothing moved.
- Refusal for any other reason (an unmerged commit, an uncommitted change, an untracked file, a non-regenerable ignored file): hand-off files stay in the worktree. The refusal test asserts this.
- Plain hand-off file (control probe): saved, then the worktree is removed.
- `--dry-run`: the same plan, never executed. Covered by the sweep test.
- `remove()` still refuses on its own when `plan.foreign` or `plan.unscanned` is set (unchanged guard, read).
- `grind_session_cleanup.after_landing`: goes through `cleanup_after_land`, so it uses the same plan and executor (read).
- `end_sessions_for` only deletes session YAML files under the main checkout's `work/.sessions/` (read).
- `--delete-local-branch` touches only the local branch ref, after a removal that succeeded (read).
- Not changed: a destination under the main checkout's `reviews_root` that is itself a symlink. That directory is the main checkout's own and outside the worktree being removed.

## Added

- `worktree_cleanup.REGENERABLE` / `regenerable()`: the ignored-file allow-list from A2.
- `worktree_cleanup._salvage_list()` / `_move_one()`: lists hand-off files from the untouched tree and moves them without overwriting a different file (A1).
- `worktree_cleanup._holds_repo()`: guard that stops the hand-off walk at any directory holding a repository, so it is never moved (F1).
- Link guard in `_salvage_list`: a hand-off dir that is, or lies under, a link refuses and is not followed (F1 class probe).
- `worktree_cleanup.CleanupPlan`, `plan_cleanup()`, `execute()`: one plan from the untouched tree and one executor that acts only without refusals; cleanup and sweep share them (F1).
- Non-regenerable ignored-file refusal, now inside `plan_cleanup` (A2).
- `worktree_cleanup._workers_in()`: finds the leaf's workers so cleanup can terminate idle ones (A1).
- `worktree_cleanup.cleanup_after_land()`: `worktree cleanup <ID>` (A1/A2/A6).
- Guard in `plan_cleanup`: refuses on a non-running, non-held active worker, and on a human-leased held worker, because `terminate` would kill or raise on it.
- `worktree_cleanup._gate()`: sweep's keep reasons. Locked, current worktree, missing directory and temp check worktrees are guards so that sweep never removes a running check's or its own worktree. The live and merged rules come from M14.2 (A3).
- `worktree_cleanup._sweep_one()` / `sweep()`: `worktree sweep` (A3/A6/A7).
- `worktree_prune.plan_worktree()`: `plan_prune`'s checks for any worktree. Added a branch-empty guard for detached worktrees.
- `session_presence.end_sessions_for()`: ends the removed worktree's and branch's session records (A6).
- `grind_session_cleanup.after_landing()` plus one call in `grind_session._run_loop`: per-leaf cleanup and the policy-driven sweep (A4). The broad `except` keeps a tidy-up failure from failing the session.
- `worktree_cli.cmd_cleanup`, `cmd_sweep`, `_add_cleanup_parsers`: the CLI.
- `DEFAULT_POLICY["worktree_sweep"]` and the schema property: the A4 policy key.
- Mocks: none.
- `tests/test_worktree_cleanup.py`:
  - `test_cleanup_saves_a_worktree_only_history_file_and_removes_the_worktree` (A1: history and RUN log saved, regenerable files allowed, idle worker terminated, worktree gone)
  - `test_a_different_same_named_hand_off_file_is_kept_beside_the_existing_one` (A1: no overwrite, same bytes not duplicated)
  - `test_cleanup_refuses_and_removes_nothing` (now also asserts hand-off files stay in place), one case each for an unmerged commit, an uncommitted change, an untracked file and a non-regenerable ignored file (A2)
  - `test_cleanup_ends_the_leafs_reviewer_and_session_records` (A6)
  - `test_regenerable_patterns` (pins the pattern semantics)
  - `test_sweep_keeps_claimed_live_and_dirty_worktrees_and_removes_the_rest` (A3: four lines, `--dry-run` removes nothing, a worktree under `.claude/worktrees/` is removed and its hand-off file saved)
  - `test_sweep_removes_a_landed_pickup_worktree_so_its_branch_can_go` (A7, `--delete-local-branch`, remote untouched)
  - `test_grind_session_cleans_up_each_landed_leaf_and_sweeps_by_policy`, with `off` and `between_leaves` cases (A4)
  - `test_cleanup_refuses_another_repository_in_the_hand_off_tree_and_moves_nothing`, with `worktree` (linked, unlanded commit, owner's `git worktree list` still valid), `clone` and `gitfile` cases (F1)
  - `test_sweep_keeps_a_worktree_holding_another_repository_in_its_hand_off_tree`, the same three cases, `--dry-run` and real (F1)
  - Helpers `_foreign` and `_foreign_intact`: build and check the three foreign-repository kinds (F1)
