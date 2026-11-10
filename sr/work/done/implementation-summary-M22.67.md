# Implementation summary: M22.67 `human-approves-over-block`

## What changed

- `specy_road/bundled_scripts/mark_implementation_reviewed.py`: on a leaf in an interactive terminal without `--yes`, when counted blocks are why the gate is not met, `_approve_over_block` runs these checks in order before anything is written (`_over_block_preflight`): the trial merge (already in `main`), the clean tree with `work/` excepted, `role_refusal()`, git identity (`recorder`), then with a remote a `git fetch <remote> <ib>` and a new `evaluate_gate` at the fetched tip (a failed fetch refuses), or with no remote that any worktree holding `<ib>` has no uncommitted tracked changes. Last, `as_if_decided(gate).passed` on that gate. Only then does `_read_reason` print each blocking record's findings, offer `[a] Approve over the block` and read the reason (an empty reason, `q` or EOF exits 0 and records nothing). `_record_over_block` makes the decision commit in a detached temporary worktree at the integration tip the gate read. The commit changes only `<prefix>roadmap/decisions.yaml` and is never on the leaf branch. With a remote it is pushed as `HEAD:refs/heads/<ib>`; with no remote the ref moves by compare-and-swap and any holder follows. Only after that does it write the marker in the checkout running the command, print the full integration commit, re-evaluate the gate (exit 1 naming the problems, registry not stamped) and return to the registry commit. If the registry commit fails while an operator decision is honoured, the command exits 1 and says the decision is recorded and how to finish. `_refuse_unmet` (moved out of `_gate_or_human_approval` to keep ruff's C901 limit) adds the interactive path and the `review operator-decision` command for a leaf with a block, plus why the option was withheld. The milestone path is unchanged.
- `specy_road/review_override.py`: `append_decision` is split out of `cmd_operator_decision`. It appends the closed entry to the ledger under the root it is given and writes no marker. `write_operator_marker` writes the marker for both callers. `as_if_decided(gate)` is a copy of the gate with every block cleared and the shortfall settled unless `signed_reviews` is on. `_recorder` and `_blocks_to_settle` were made public (`recorder`, `blocks_to_settle`) with no change in behaviour. `review operator-decision`'s output and tests are unchanged.
- `specy_road/nested_repos_land.py`: two new public steps. `in_temp_worktree(repo, tip, callback)` adds the worktree, runs the callback and removes it. `move_ref(repo, ref, tip, new, holder, what)` does the compare-and-swap `update-ref` and then `_follow_in_checkout`. `_checked_out_in` is now public as `checked_out_in`. `_merge_in_temp_tree` stays private and does the feature-branch merge on top of `in_temp_worktree`, for `_land_one` and `_land_one_locally` only. `_land_one_locally` calls `move_ref(..., "the merge")`, so its messages are byte-identical. The temporary directory keeps the `specy-road-nested-land-` prefix, so `doctor_worktrees.TEMP_WORKTREES` still recognises it.
- `specy_road/review_eligible.py`: `_human_text` gives the human row. A milestone (no registry branch) keeps the id form. A leaf gets the id-less command on its branch, in one of three forms (no block / settling would pass / would not pass), and ` --sign-key <your private key>` stays inside the command.
- `docs/orchestration-review.md` (operator section and the human row), `CHANGELOG.md` `[Unreleased]`.

Touch zones confirmed: no change was needed outside them. `review_cli.py` passes `branch` to `reviewer_eligibility` already, and `tests/test_milestone_full_review.py` is unchanged and passes.

## Verification

- `pytest -n 4 tests/test_review_override.py tests/test_review_eligible.py tests/test_mark_implementation_reviewed_gate.py tests/test_milestone_full_review.py tests/test_nested_repo_land_modes.py`: 132 passed.
- Full suite in three chunks (`-n 4`): 2068 + 2507 + 2647 passed, 18 skipped. One failure, `tests/test_worker_max_workers_global.py::test_a_resumed_completed_worker_leases_only_while_its_turn_runs`, is flaky: it failed in 3 of 5 runs, passes alone, and its file touches none of these modules.
- `specy-road file-limits`, `specy-road validate` / `export --check` / `digest --check` (dogfood fixture): pass. `ruff check` on the changed files: clean.

## Unanswered questions

- When the person runs with no remote and the main checkout itself has the integration branch checked out (and is clean), that checkout's files follow the ref, as `land: local` does. The sheet accepts this under accepted limits; there is no dedicated test beyond the linked-worktree holder row.

## Added

- `review_override.append_decision`: the one ledger-entry write shared by `review operator-decision` and the new path (A1).
- `review_override.write_operator_marker`: the marker write both callers do after their entry lands (A1).
- `review_override.as_if_decided`: the "settling every block (and the shortfall unless signed) would pass" check, shared by the command and `handoff status` (A1, A3).
- `nested_repos_land.in_temp_worktree`: public temporary-worktree-plus-callback step (A2).
- `nested_repos_land.move_ref`: public compare-and-swap-and-follow step (A2).
- `mark_implementation_reviewed._integration`: splits the policy ref into remote and branch (push vs ref move).
- `mark_implementation_reviewed._over_block_preflight`: every refusal before the menu, in the sheet's order (A1, A4).
- `mark_implementation_reviewed._read_reason`: findings, `[a] Approve over the block`, reason prompt; EOF branch is quit (input closed in a TTY).
- `mark_implementation_reviewed._record_over_block`: temporary-worktree commit, push or ref move, marker, printed commit, second gate check (A1, A2, A5); its `ValueError` branch is an old copied decisions schema, as in `review operator-decision`.
- `mark_implementation_reviewed._approve_over_block`: ties preflight, prompt and record together.
- `mark_implementation_reviewed._refuse_unmet`: the refusal text, moved out to keep `_gate_or_human_approval` under ruff's complexity limit; adds the A4 lines.
- `CalledProcessError` guard around `_commit_registry_approved` in `main`: a failed registry commit after an honoured operator decision (A5); re-raises otherwise.
- `review_eligible._human_text`: the human row's leaf and milestone forms (A3).
- Tests in `tests/test_review_override.py`: `Layout`/`_layout` (root and sr/ fixtures with the gate on, optional bare origin and leaf worktree), `_terminal` (patched TTY and `input`, records stdout before each prompt), `_mark`, `_blocked`, `_assert_decision_landed`; `_block` gains `extra` (for `--sign-key`) and removes its notes file (it sits inside the git checkout for sr/). Rows: local root/sr × role unset/`coordinator`; remote root/sr including `finish-this-task`; clean holder; withheld (dirty holder, unclean tree, identity, policy pin, strong_review); signed-review shortfall; role parametrized over six values; empty reason / quit; `--yes` / non-TTY; stale policy pushed by a second clone; refused push (pre-receive hook); refused registry commit (pre-commit hook); milestone block unchanged.
- Tests in `tests/test_review_eligible.py`: the existing human-row assertion now pins the id-less leaf form (sheet-directed); one parametrized test for the two block forms (opus and sol blocking, settling passes; opus blocking with an unmet `strong_review` item).
- Mocks: `sys.stdin.isatty` and `builtins.input` only (the sheet's TTY definition).
