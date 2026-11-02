# Implementation summary: M11.4 — max_workers counts live workers across checkouts and applies to resumes

Branch `feature/rm-max-workers-global`, base `be6a6a63`.

## What changed

- **Linked worktrees** already shared one count: `work/.workers/` resolves to the main checkout from any linked worktree (`review_files.reviews_root`). No code change; a test now shows it.
- **Separate clones** (`specy_road/worker_ops.py`, `claimed_elsewhere`): each clone keeps its own `work/.workers/`, so the shared source is the integration branch's registry. The new function counts a leaf when the registry on `refs/heads/<integration>` or `refs/remotes/<remote>/<integration>` (as last fetched) claims it with `owner` equal to this checkout's `git config user.name`, and the claim's branch has no local branch in this repository. Pickup writes that owner by default and creates the branch only in the clone that picked the leaf up, so each clone counts the other's leaves and not its own. Leaves that already have a local record, and the leaf being launched or resumed, are excluded. No fetch is run: delegate stays offline, and the docs say to fetch first.
- **Slot check** (`_slot_or_existing`): it reads `policy.max_workers` itself and counts other active records plus `claimed_elsewhere`. It takes `own=` so a resumed worker does not count itself. When the refusal includes other clones' claims, the error names them (`N workers active (and K claimed in other clones: …), policy max_workers is L`). With none, the message is unchanged.
- **message / resume** (`_send`): every resumed turn now takes the slot check, not only a `failed` one. An `idle`/`completed` worker still resumes in its own slot. It is refused when the other counted workers already reach the limit: a lowered limit, or another clone's claims. The refusal for "another worker holds the leaf" now names the record's actual state.
- **Docs** (`docs/orchestration-workers.md`): a new "What `max_workers` counts" paragraph (A2) covers which records are counted, how worktrees share them, and how a clone is included through owned claims on the integration branch. It also covers fetch staleness, that a claim counts whether a worker or a person holds it, and that claims with another owner, or none, are not counted. The `delegate` text and the `resume` table row now point to it.
- **File-limit housekeeping in `worker_ops.py`**, needed to stay at 400 lines with no behaviour change: removed the unused `_now`, a doubled blank line in the imports and the two trailing blank lines, folded `_wrapper_gone`'s docstring onto one line, and replaced `adopt`'s inner `fn` with an equivalent `mutate` lambda.

## Acceptance

- **A1:** `delegate`, `message` and `resume` refuse a launch that would exceed `max_workers`. The count covers the main checkout, its linked worktrees (they share records) and clones (owned claims on the integration branch).
- **A2:** the docs paragraph described above.
- **A3:** `tests/test_worker_max_workers_global.py`: an idle worker's resume is refused at the limit (lowered limit, and another clone's claim). Two clones share one limit (`delegate` refused by the other clone's claim, and each clone counts the other's), and a linked worktree is refused by the main checkout's worker.

## Touch zones (confirmed)

Changed: `specy_road/worker_ops.py`, `docs/orchestration-workers.md`, `tests/`. `worker_state.py` and `orchestration_config.py` needed no change. No path outside the zones was needed: the registry readers (`registry_remote_overlay_merge.read_registry_at_ref`, `git_workflow_config.resolve_integration_defaults`, `git_config_user_name`) are reused as they are.

## Verification

- `python -m pytest tests -k "worker or orchestr or review_round"`: 432 passed.
- The rest of `tests/`, in two halves: 1403 passed, 2 skipped, 1 failed (`test_lean_gates::test_private_imports_pass_on_committed_baseline`, which caught a new test reaching `_slot_or_existing`). I rewrote that test to use `worker delegate`; then `tests/test_worker_max_workers_global.py tests/test_lean_gates.py` gave 18 passed, 2 skipped. Second half: 1150 passed.
- `specy-road file-limits`: OK. `ruff check` on the changed Python files: clean.

## Added

- `worker_ops.claimed_elsewhere(repo_root, skip)`: the cross-clone count (A1); public so the docs and tests can name it.
- `_slot_or_existing(..., own=)` keyword: lets a resumed worker leave itself out of the count, so an idle worker resumes in its own slot.
- `_slot_or_existing` reads `policy.max_workers` itself (the `limit` parameter is gone): every caller read it the same way, and this kept the file within 400 lines.
- Error suffix `(and K claimed in other clones: …)`: says why a launch is refused when no local record explains it.
- `_send` slot check for every state (it was `failed` only): A1 for message/resume.
- Test `test_each_clone_counts_the_others_claims`: both directions of the clone count, and no double counting of a local leaf.
- Test `test_two_checkouts_share_one_limit`: A3, `delegate` refused by another clone's claim, nothing recorded.
- Test `test_a_claim_by_another_user_is_not_counted`: the owner filter, so a teammate's claims do not take the coordinator's slots.
- Test `test_a_linked_worktree_counts_the_main_checkouts_workers`: A1 for worktrees, through `worker delegate`.
- Test `test_an_idle_worker_resumes_in_its_own_slot`: guards against a resume counting itself at `max_workers: 1`.
- Test `test_a_resume_is_refused_when_other_workers_fill_the_limit`: A3, resume refused at the limit (lowered limit), with no message event recorded.
- Test `test_a_resume_is_refused_when_another_clone_fills_the_limit`: A3, resume refused by another clone's claim.
- Test helpers `_clone_with_claim`, `_idle`: build a second clone that pushes an owned claim, and an idle worker with a session id.
- Mocks: none.
