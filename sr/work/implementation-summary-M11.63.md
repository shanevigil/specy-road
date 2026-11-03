# Implementation summary: M11.63 `pickup-second-claim-guard`

## What changed

`do-next-available-task` now refuses a second claim in a checkout that already holds one. Right after roadmap validation, and before any fetch, registry commit, push or branch switch, it reads the registry. If a row's branch exists locally and no other worktree has it checked out, pickup exits `6` (grind-session's `EXIT_IN_FLIGHT`). The message names the held node and branch, lists any further held claims, and suggests `finish-this-task`, `abort-task-pickup` or `--allow-second-claim`. With `--allow-second-claim`, pickup proceeds as before.

The guard reuses grind-session's held-claim test, `own_in_flight_claims` from `grind_session_in_flight.py`. It passes all registry node ids instead of the plan's active set, and a `branch_exists` probe that also excludes branches checked out in another worktree.

That exclusion is load-bearing. A coordinator runs `do-next-available-task --worktree` repeatedly from the main checkout, and every leaf branch it creates exists in the same repository. Without the exclusion, the second `--worktree` pickup would exit 6. A claim whose branch is gone (another clone's, or a dead row) is not held here and never blocks. Neither is a claim whose leaf is already Complete on its branch. In `on_complete: pr` mode, finish releases the row only on the feature branch, so the integration branch keeps it until the PR merges. Without this filter, the next pickup from the integration branch exited 6 and suggested `abort-task-pickup`, which deletes the finished work. The filter reuses `node_complete_on_ref`, the check grind-session uses for `branch_complete`.

The AGENTS.md stub's "When nothing is pickable" bullet now reads: exit `6` is a claim this checkout holds — finish it, `abort-task-pickup`, `--resume-in-flight` (grind) or `--allow-second-claim`. The old text said "this clone" and offered only grind's `--resume-in-flight`, which pickup does not have. The new clause is 131 bytes, the same as the old one, because `tests/test_enforced_rules_pointers.py::test_the_meter_reports_a_shorter_section_than_before` caps the rendered section below 7,679 bytes and the old section measured 7,678. A longer first wording (naming `do-next-available-task` explicitly) failed that test, so it was cut back; no other stub text was touched. The bullet's provenance comment names the new enforcement point (comments are not metered).

## Touch zones (final)

- `specy_road/bundled_scripts/do_next_task.py`: one import, one call in `_run_pickup`. After the WIP merge it is 384 lines; cap 400.
- `specy_road/bundled_scripts/do_next_task_args.py`: `--allow-second-claim`.
- `specy_road/templates/specyrd/agents-md-block.md`: the exit-6 text and its provenance comment.
- `tests/test_pickup_second_claim_guard.py`: new.
- **Added outside the listed zones:** `specy_road/bundled_scripts/do_next_task_held_claim.py`. `do_next_task.py` was at 394 of its 400-line cap, so the guard went into a new module, as the executor rules direct. Please add it to the leaf's touch zones.

## Follow-up for the maintainer

`sr/AGENTS.md` embeds the stub block. It is outside this leaf's zones, so after this lands it reads as stale until `specy-road refresh-stubs` is run there.

## Verification

- **Review round 1 (Opus reviewer blocked; Grok approved):** fixed the `on_complete: pr` regression above and added `test_a_leaf_finished_in_pr_mode_does_not_block_the_next_pickup`. The sequence is: pickup `--on-complete pr`, commit, `finish-this-task --on-complete pr`, `git checkout main`, then pickup exits 0 and claims M2. Red-green: without the filter, that test gets exit 6. Post-fix: the leaf's tests plus neighbours (`test_do_next_finished_unmerged`, `test_do_next_pr_gating`, `test_grind_session_in_flight`, pickup, worktree, claim-trap and stub tests) → 97 passed; `specy-road file-limits` → OK.
- **Merge of `origin/WIP/improvements-0-3-1` (2026-11-03):** clean. WIP's new `pickup_finish_lock` split `main` into `_run_pickup`, and the guard call moved there with it. WIP's own `do_next_task.py` was exactly 400 lines, so with the guard it came to 402 and failed `specy-road file-limits`. I moved `_validate_or_exit` verbatim into `do_next_task_held_claim.validate_or_exit(repo_root)` to fix that; there is no behaviour change and nothing outside the file referenced it. Post-merge: `tests/test_pickup_second_claim_guard.py` and neighbours → 63 passed; every test file that drives pickup (31 files) → 351 passed; `specy-road file-limits` → OK.

- `python -m pytest tests/test_pickup_second_claim_guard.py -q` → 5 passed (6 after review round 1).
- `python -m pytest -q tests/test_agents_md_block.py tests/test_pickup_worktree.py tests/test_grind_session_in_flight.py tests/test_claim_traps.py tests/test_do_next_task_pickup.py` → 50 passed.
- `python -m pytest -q tests/test_enforced_rules_pointers.py tests/test_agents_md_block.py tests/test_worker_faults.py tests/test_worker_resume_failed.py tests/test_pickup_second_claim_guard.py` → 61 passed.
- `python -m pytest -n auto -q` → 3323 passed, 2 skipped on the final code and stub (the stub test above was added during that run and was run separately: 5 passed). (an earlier run with the longer stub wording failed the meter test above; `test_worker_faults` and `test_worker_resume_failed` also failed once under a load average of ~40 and pass on rerun; they do not touch this code).
- `specy-road file-limits` → OK.
- Red-green: with the `refuse_second_claim` call replaced by `pass`, the refusal test fails. With the other-worktree exclusion removed, the worktree test fails.

## Added

- `do_next_task_held_claim.branches_in_other_worktrees`: parses `git worktree list --porcelain` for branches held by worktrees other than this git root, so a `--worktree` coordinator's leaves are not counted as this checkout's.
- `do_next_task_held_claim.held_claims`: feeds all registry node ids (deduplicated) to the existing `own_in_flight_claims` with a probe that excludes other worktrees' branches. It reuses grind-session's test instead of a second definition of "mine".
- Filter in `held_claims` on `node_complete_on_ref`: a leaf Complete on its own branch (finished, PR not merged) is not a held claim, so the PR-per-leaf flow is not blocked or told to abort finished work (review round 1).
- Test `test_a_leaf_finished_in_pr_mode_does_not_block_the_next_pickup`: the CLI regression for that case (review round 1).
- `do_next_task_held_claim.refuse_second_claim`: the guard itself. It prints the held claim(s) and the way out, and raises `SystemExit(6)`; `allow` short-circuits it.
- `do_next_task_held_claim.validate_or_exit`: `do_next_task._validate_or_exit` moved verbatim (body, comment and message unchanged; takes `repo_root` instead of the `ROOT` global), so `do_next_task.py` fits its 400-line cap after the WIP merge.
- Guard call in `do_next_task._run_pickup` (was `main` before the merge) after `_validate_or_exit()`: refuses before anything is fetched, committed, pushed or switched.
- `--allow-second-claim` flag in `do_next_task_args._add_claim_visibility_args`: the override A1 requires.
- Test `test_second_pickup_exits_6_naming_the_held_claim_and_claims_nothing`: refusal, exit 6, held claim named, `main`/`origin/main`/registry/branches unchanged.
- Test `test_allow_second_claim_picks_up_the_next_leaf`: the override.
- Test `test_a_claim_whose_branch_is_gone_does_not_block`: a registry row whose local branch was deleted does not count.
- Test `test_claims_checked_out_in_other_worktrees_are_theirs_not_this_checkouts`: two `--worktree` pickups from one main checkout both succeed.
- Test `test_the_agents_md_stub_describes_pickups_exit_6_and_its_override`: pins A1's "stub matches the command" half. The rendered stub's exit-6 clause names this checkout's claim, grind's `--resume-in-flight` and `--allow-second-claim`, and the parser accepts that flag.
- Test helper `_two_leaves`: extends `test_baseline_gate_cli._project` with a second authored leaf so a second pickup has something to claim.
- Test helper `_registry`: reads the registry at a ref.
- Mocks: none.
