# Implementation summary: M12.5

`specy-road worktree cleanup <ID>` and `specy-road worktree sweep [--dry-run] [--delete-local-branch]`
retire landed worktrees, moving their hand-off files to the main checkout first.

## What changed

- **`specy_road/worktree_cleanup.py` (new).**
  - `salvage` moves `work/reviews/<ID>/**` (cleanup) or `work/reviews/**` (sweep) from the worktree's own tree into `reviews_root(main)`. A file with the same bytes already there is dropped from the worktree. A different file is kept beside the existing one as `<name>.from-worktree<n>`.
  - `cleanup_after_land` (A1/A2/A6) does these steps in order:
    1. salvage;
    2. `plan_worktree`, which holds `plan_prune`'s checks, M14.3's foreign-worktree refusal included;
    3. refuse on ignored files that are neither in `REGENERABLE` nor salvaged, on a non-running active worker that is not idle, completed or paused (for example `starting`), or on a worker handed to a human;
    4. terminate the leaf's held workers;
    5. `remove(plan)`;
    6. `session_presence.end_sessions_for`.
  - `sweep` (A3/A7) first runs `terminate_orphaned`, except in `--dry-run`. It then judges every linked worktree from `git worktree list` with M14.2's rules: `live_holders` plus `_live`, and `classify`/`evidence_kind`/`merged_how` for "merged with own commits". A detached `HEAD` must be contained in the integration branch. Each worktree then gets the same salvage and unsaved-work checks, and the output is one line: `removed`, `would remove`, or `kept <path>: <reason>`. Locked worktrees, the current worktree, missing directories and `TEMP_WORKTREES` (running specy-road checks) are kept. `--delete-local-branch` reuses `grind_session_cleanup.delete_local_branch` against the integration ref. Remote branches are never deleted (A5).
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

- `pytest -q -n 4 tests/test_worktree_cleanup.py`: 12 passed.
- `pytest -q -n 4` (full suite): 4412 passed.
- `specy-road file-limits`: OK.
- `specy-road validate --repo-root tests/fixtures/specy_road_dogfood`: exit 0.
- `python scripts/check_test_private_imports.py` and `python scripts/check_clones.py`: exit 0.

## Added

- `worktree_cleanup.REGENERABLE` / `regenerable()`: the ignored-file allow-list from A2.
- `worktree_cleanup.salvage()` / `_move_one()`: moves hand-off files without overwriting a different file (A1).
- `worktree_cleanup._unsaved()`: the non-regenerable ignored-file refusal (A2).
- `worktree_cleanup._workers_in()`: finds the leaf's workers so cleanup can terminate idle ones (A1).
- `worktree_cleanup.cleanup_after_land()`: `worktree cleanup <ID>` (A1/A2/A6).
- Guard in `cleanup_after_land`: refuses on a non-running, non-held active worker, and on a human-leased held worker, because `terminate` would kill or raise on it.
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
  - `test_cleanup_refuses_and_removes_nothing`, one case each for an unmerged commit, an uncommitted change, an untracked file and a non-regenerable ignored file (A2)
  - `test_cleanup_ends_the_leafs_reviewer_and_session_records` (A6)
  - `test_regenerable_patterns` (pins the pattern semantics)
  - `test_sweep_keeps_claimed_live_and_dirty_worktrees_and_removes_the_rest` (A3: four lines, `--dry-run` removes nothing, a worktree under `.claude/worktrees/` is removed and its hand-off file saved)
  - `test_sweep_removes_a_landed_pickup_worktree_so_its_branch_can_go` (A7, `--delete-local-branch`, remote untouched)
  - `test_grind_session_cleans_up_each_landed_leaf_and_sweeps_by_policy`, with `off` and `between_leaves` cases (A4)
