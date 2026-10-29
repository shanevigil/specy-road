# Implementation summary for M3.13

## Summary

Before reviewers run and before finish, the toolkit trial-merges the integration branch into the leaf's branch. It uses `git merge-tree --write-tree`, which merges in memory with no checkout, index or working-tree change.

- **A1:** `review-packet` adds a `Trial merge` line to the packet header. It says whether the branch is up to date, merges cleanly, conflicts only on bookkeeping, or conflicts on code. For a code conflict it names the files and adds a bold **Stop** line telling the executor to merge and resolve before review. `handoff status` (text and `--json`) puts the same conflict message first in the node's `problems`. For any conflict, it also carries a `trial_merge` entry naming every conflicted file, and the text output labels a bookkeeping-only conflict as not blocking.
- **A2:** `mark-implementation-reviewed` and `finish-this-task` exit 1 while a trial merge of `HEAD` conflicts on any path outside `work/`, `roadmap/`, `planning/`, `roadmap.md` and `roadmap-context.md`. The error names the files and the `git merge <ref>` to run. mark checks before the summary is shown, a human approves, or `REVIEW-human.md` is written. finish checks before the review-gate check and before any status, registry or bookkeeping write.
- **A3:** Tests cover a clean trial merge, a bookkeeping-only conflict (allowed) and a code conflict (refused). They run through the packet, `handoff status`, `mark-implementation-reviewed --yes` and `finish-this-task`, plus the git helper.

The integration ref is the one the rest of the toolkit uses (`finish_implementation_check.base_ref`): the remote-tracking branch as last fetched, else the local branch. Nothing here fetches, so `review-packet` and `handoff status` stay offline and read-only. When git cannot answer (no integration ref, an unknown ref, git older than 2.38 with no `--write-tree`), the packet says "git could not answer" and mark and finish go ahead. This matches the toolkit's existing "say nothing" rule for best-effort git.

## Changes

- `specy_road/git_subprocess.py`: `merge_conflicts(repo_root, ours, theirs)`. It returns the conflicted paths, `[]` when clean, or `None` when git cannot answer. It runs at the repository top level, because `merge-tree` names paths relative to the working directory, so the names are always repository-root names.
- `specy_road/review_gate.py`: `TRIAL_MERGE_BOOKKEEPING`, `is_trial_merge_bookkeeping`, `TrialMerge` (`conflicts`, `code_conflicts`, `problem()`), `trial_merge(repo_root, ref, integration_ref)` and `trial_merge_or_exit(repo_root)`. `trial_merge` rebases every conflicting path to the project with `rebase_to_project`. A path that does not rebase lies outside the project: it always blocks and is shown `../`-relative to the project root. A path that does rebase is bookkeeping only if it is exactly `roadmap.md` or `roadmap-context.md`, or lies below `work/`, `roadmap/` or `planning/`.
- `specy_road/bundled_scripts/review_packet.py`: `_trial_merge_line` in the header.
- `specy_road/bundled_scripts/review_cli.py`: the `handoff status` problems list leads with the trial-merge problem.
- `specy_road/bundled_scripts/mark_implementation_reviewed.py`, `specy_road/bundled_scripts/finish_task.py`: call `trial_merge_or_exit(ROOT)`. In finish it runs after M4.10's `delete_branch_preflight`, before M3.14's scaffold-sheet check and before the review check. I had removed finish_task.py's empty `# Git helpers` banner to fit the 400-line cap. M4.10 moved the argument parsing out (349 lines), so the banner is restored and this file's diff against WIP is just the import and the call.
- `docs/orchestration.md` (at the 400-line cap, so I extended the existing "Order:" bullet rather than adding lines) and `docs/dev-workflow.md` (review step 2 and finish step 1).

Final touch zones are the widened list on the claim. Every changed path is inside it: the eight original zones plus `specy_road/bundled_scripts/review_cli.py` and `specy_road/review_gate.py`. Nothing else was needed.

## Review round 1 (Sol, at d2215f8): A2 block, fixed

- **Lookalike paths:** `code_conflicts` used `startswith` for every allowance, so `roadmap.md.backup` counted as bookkeeping. Now files match exactly and directories match only below `dir/`.
- **Paths outside the project:** these are now always code conflicts, as asked. One correction to the finding's mechanism: at d2215f8, `merge-tree` ran in the project root and named paths relative to it. A git-root `roadmap/x.json` came back as `../roadmap/x.json`, which already blocked, so the exact scenario in the finding did not happen there. That cwd-relative naming was itself a latent bug, though. `rebase_to_project` was being applied to names that were already project-relative, and the fall-back to the raw name is all that kept `sr/roadmap/registry.yaml` classified as bookkeeping. `merge_conflicts` now runs at the top level, so it returns repository-root names, as its docstring says. Rebasing is then real, and a path that does not rebase is a code conflict.
- **Deviation:** a file named exactly `work`, `roadmap` or `planning` is a code conflict, not bookkeeping, which is stricter than `path == dir`. Conflicted paths are files, and a file named `roadmap` is not under `roadmap/`.
- **Dropped hint:** the refusal no longer prints the hint listing the allowed paths. It had to go to stay within the 400-line cap, and the error already names only the blocking files.

## Merge with WIP (6bcfeb8, after M4.10 landed)

- **Conflict:** the only one was `specy_road/bundled_scripts/finish_task.py` in `_resolve_main_context`. I kept both sides: M4.10's `delete_branch_preflight` (a flag and mode check, no git) first, then `trial_merge_or_exit`. Everything else merged automatically. The claim row and its touch zones are unchanged.
- **Inherited failures, not touched (outside M3.13's zones):**
  - `tests/test_finish_task_commands.py::test_finish_already_done_on_branch_when_complete_and_deregistered` fails on WIP's tip `6bcfeb8` without this branch. M4.10's `retry_milestone_rollup_landing` (`specy_road/finish_milestone_rollout.py:120`, reached from `feature_rm_registry.py:120`) loads the real roadmap, but the test patches `load_roadmap` only in `feature_rm_registry`.
  - `ruff check` reports C901 on `tests/test_grind_session.py:57` (`__init__` complexity 11). That is also present on `6bcfeb8`.

## Merge with WIP (ce4225e, after M3.12, M3.14 and M3.15 landed)

Both reviewers approved `ead181e`. WIP then moved 48 commits ahead, and this leaf's own check reported code conflicts (`handoff status`: `docs/dev-workflow.md`, `finish_task.py`, `tests/test_review_cli.py`). I merged at `c8b6e9a`, keeping both sides of each conflict. The merge adds no new behaviour, and it makes the earlier approvals stale.

- `specy_road/bundled_scripts/finish_task.py`: `_resolve_main_context` runs `delete_branch_preflight`, then `trial_merge_or_exit`, then M3.14's `scaffold_planning_or_exit`, then the review gate. None of these write. The import line takes both.
- `docs/dev-workflow.md` finish step 1: states both refusals, trial merge first, then the scaffold sheet, then the review gate.
- `tests/test_review_cli.py`: imports both M3.15's `NODE` and this leaf's `diverge`.
- `review_cli.py` auto-merged. M3.15's `handoff status` exit code comes from `state` alone. So a node whose gate is met still exits 0 while listing a trial-merge conflict under `problems`. A1 asks only for the report, so I left M3.15's exit contract as it was.
- The two inherited failures from the previous merge are fixed on WIP (`4d5775c` and others), so every gate now exits 0.
- WIP has since moved 2 more commits (`86b476e`: a roadmap chunk and `sr/tools/*.sh`). A trial merge against it is clean, so I did not merge again.

## Review round 3 (Sol, at a89f6d6): A1 block, fixed

- **Finding:** `handoff status` added only `TrialMerge.problem()`. That is `None` for a bookkeeping-only conflict, so neither the text nor the JSON named the conflict or its files. The old status test asserted that omission.
- **Fix (`e47c4c0`, `review_cli.py` only):** the node status now has `trial_merge`, which is `null` when the branch merges cleanly, is up to date, or git cannot answer. Otherwise it is `{ref, behind, conflicts, blocking}`: `conflicts` lists every conflicted path and `blocking` the non-bookkeeping ones. The text renders one line, `trial merge with <ref>: conflicts on <every path>`, ending in `(bookkeeping only, which does not block)` when `blocking` is empty. A code conflict still adds its blocking message to `problems`, and mark and finish are unchanged. So a bookkeeping-only conflict is reported and still allowed. `_unclaimed` sets `trial_merge: null` so every node in the JSON has the same keys. `review_gate.py` is at the 400-line cap, so the change stays in the CLI.
- `docs/dev-workflow.md` review step 2 now says a bookkeeping-only conflict is reported too, and labelled as not blocking. `docs/orchestration.md` already says `handoff status` reports the trial merge.
- **Mutation check:** against the committed `review_cli.py` from `a89f6d6`, all three cases of the extended test fail.

## Merge with WIP (e61f1b2, after worker-reconcile-and-status landed)

After the round-3 fix, a trial merge against WIP conflicted on `specy_road/bundled_scripts/review_cli.py`, so I merged before hand-off (`0dc622d`). The commit message names `29e2469`, the worker-reconcile commit behind the conflict. The WIP tip it actually merged is `e61f1b2`.

- `_node_status` `problems` keeps both sides: the trial-merge problem first, then WIP's `_executor_verify_problems(ready)` in place of `verify_problems(ready)`. The `trial_merge` field and its render line sit beside WIP's new `commands_rerun` review line. Everything else merged automatically.
- **Inherited failure, not touched (outside M3.13's zones):** `specy-road file-limits` and `tests/test_validate_file_limits.py::test_file_limits_passes_on_repo` fail on `specy_road/bundled_scripts/worker_cli.py` (408 lines) and `specy_road/worker_adapters.py` (430 lines). Both are byte-identical to WIP's `e61f1b2`, and the roadmap gives the fix to M3.16 ("brings two worker modules back under the file cap").

## Merge with WIP (065e4cc, after M3.11 landed) and the `--base` fix

- **Merge (`5a0235c`):** the only conflict was `tests/test_review_packet.py`. M3.11's `-o` copy assertions stay at the end of `test_main_writes_packet_file`. This leaf's trial-merge packet test follows, then M3.11's `--base` test. `review_packet.py` merged automatically.
- **Fix (`26d9905`):** M3.11's `review-packet --base <ref>` replaces `ReviewTarget.base_ref` to move the diff range. After the merge, the packet's `Trial merge` line followed it, so it could say "up to date with" an arbitrary ref while mark and finish check the integration branch. `build_packet` now keeps the integration ref from before `--base` and passes it to `_header` and `_trial_merge_line`. The diff range is unchanged.
- `test_packet_reports_trial_merge_with_integration_branch` now also builds each case with `--base` at the branch tip. With the integration ref taken after `--base` (the auto-merged behaviour), all three cases fail.
- **Inherited failures, not touched (outside M3.13's zones):** the file-limits failure above, plus `tests/test_unauthored_leaf_guard.py::test_validate_notes_complete_leaves_still_on_the_scaffold[False/True]`. There `validate` now prints two `notice:` lines (the scaffold notice and the orchestration-starter notice) where the test expects one. Both cases fail the same way in a clean worktree at WIP's `065e4cc`, and this branch's diff against `065e4cc` touches no validate code.
- WIP is 1 commit past `065e4cc`. A trial merge against it is clean, so I did not merge again.

## Merge with WIP (d927f96, after M4.17 landed)

WIP moved ahead; a trial merge conflicted on `specy_road/bundled_scripts/review_cli.py` with M4.17. Merge `e76d5b4` keeps both behaviours. Everything else merged automatically.

- `_node_status` still computes `trial_merge` and puts its blocking `problem()` first in `problems`, then M4.17's gate problems, executor-verify problems and `loop.problems()`. JSON still carries `trial_merge` (conflicts, blocking) beside M4.17's `escalation` / `escalated` state.
- `_render` prints the trial-merge line, then the escalation line.
- `_unclaimed` still sets `trial_merge: None`. `review list` and `archive_review` stay as M4.17 left them.
- **Inherited, not touched:** `specy-road file-limits` reports `specy_road/bundled_scripts/role_prompt.py` at 407 lines. That is WIP's M3.18 work, outside this leaf's zones.

## Verification

- At `26d9905`: full `pytest -q -p no:cacheprovider -rf` gave 2420 passed, 2 skipped and 3 failed (all inherited, listed above). `tests/test_review_packet.py` gave 12 passed, and `ruff check specy_road tests` passed.

- After the e61f1b2 merge: full `pytest -q -p no:cacheprovider -rf` gave 2418 passed, 2 skipped and 1 failed (the inherited file-limits test above). The focused and `handoff status` test files gave 188 passed, and `ruff check specy_road tests` passed.
- Round 3: full `pytest -q -p no:cacheprovider -rf` at `e47c4c0` gave 2402 passed and 2 skipped. The focused files gave 117 passed, and the other `handoff status` and docs tests (`review_hardening`, `review_evidence`, `worker_cli`, `session_presence`, `review_signing`, `review_round6_evidence`, the docs tests) gave 86 passed. `specy-road file-limits` was OK, `ruff check specy_road tests` passed, and `git diff --check` was clean.
- After the ce4225e merge: full `pytest -q -p no:cacheprovider -rf` gave 2402 passed and 2 skipped. The focused files (`review_packet`, `review_cli`, `mark_implementation_reviewed_gate`, `finish_task_commands`, `git_subprocess`, `review_gate`, `finish_bookkeeping_wiring`, `project_layouts`) gave 117 passed. `specy-road file-limits` was OK, `ruff check specy_road tests` passed, and `git diff --check` was clean.
- After the 6bcfeb8 merge: full `pytest` 2365 passed, 2 skipped, 1 failed. The failure is the inherited M4.10 test above.
- After the merge, the focused tests for both leaves (this leaf's files plus `test_branch_cleanup`, `test_rollup_branch_cleanup` and the `test_finish_*` files): 182 passed, 1 failed (the same inherited test).
- Round 0: full `pytest` 2310 passed, 2 skipped. The full suite was not re-run for round 1.
- Round 1: `pytest tests/test_review_packet.py tests/test_review_cli.py tests/test_mark_implementation_reviewed_gate.py tests/test_finish_task_commands.py tests/test_git_subprocess.py tests/test_review_gate.py tests/test_finish_bookkeeping_wiring.py tests/test_project_layouts.py` → 115 passed.
- Round 1 mutation checks: against d2215f8's `review_gate.py` and `git_subprocess.py`, the `roadmap.md.backup` case fails. Classifying an unrebased path by its raw name, or running `merge-tree` in the project root, fails the nested layout test.
- `specy-road file-limits` → OK. `ruff check specy_road tests` passed before the merge; after it, the only error is the inherited `tests/test_grind_session.py:57`.
- Mutation check: with `merge_conflicts` forced to return `[]`, the six code-conflict and bookkeeping tests fail.
- Composer-2.5 executor (at `c5ac660`): `pytest tests/test_review_packet.py tests/test_review_cli.py tests/test_mark_implementation_reviewed_gate.py tests/test_finish_task_commands.py tests/test_git_subprocess.py tests/test_review_gate.py tests/test_finish_bookkeeping_wiring.py tests/test_project_layouts.py -q -p no:cacheprovider -rf` → 118 passed; `specy-road file-limits` OK; `ruff check specy_road tests` passed.
- After the d927f96 merge (`e76d5b4`): the same focused files plus `tests/test_review_rca.py` → 128 passed. `ruff check specy_road/bundled_scripts/review_cli.py tests/test_review_cli.py tests/test_review_rca.py` passed. `review_cli.py` is 376 lines.

## Notes for reviewers

- "Allowed" for bookkeeping means only that review and finish do not refuse. The landing still resolves only `roadmap/registry.yaml`, `roadmap.md` and `roadmap-context.md` deterministically. A conflict on a roadmap chunk, a planning sheet or a `work/` file can still stop a merge-mode landing after the bookkeeping commit, as it could before this change. The allowed set follows the coordinator's instruction for this leaf.
- In milestone-rollup finishes the check still runs against the integration branch, not the rollup branch.
- Merging the integration branch after review makes earlier reviews stale, by design: the merge commit becomes the commit under review.

## Added

- `git_subprocess.merge_conflicts`: the one in-memory trial-merge primitive. The guard `code not in (0, 1) or empty tree id` returns `None`, because an unknown ref also exits 1 with nothing on stdout. A test reaches it with `no-such-ref`.
- `git_subprocess.merge_conflicts` top-level run (round 1): makes names repository-root. A non-repository falls through to `merge-tree` failing and returns `None`, which a test reaches.
- `review_gate.TRIAL_MERGE_BOOKKEEPING`: the allowed paths, from the coordinator's instruction.
- `review_gate.is_trial_merge_bookkeeping` (round 1): exact-file and whole-directory matching (Sol, A2).
- `review_gate.TrialMerge` / `trial_merge`: shared by the packet, `handoff status`, mark and finish so all four agree. The `None` branch covers no integration ref or git unable to answer, so callers say nothing. The outside-project branch (round 1) makes a path that does not rebase a code conflict.
- `review_gate.trial_merge_or_exit`: A2's refusal, shared by mark and finish.
- `review_packet._trial_merge_line`: A1's packet report (up to date / clean / bookkeeping-only / code conflict). After the 065e4cc merge, it takes `(ref, integration_ref)`, and `build_packet` captures `integration_ref` before `--base`, so `--base` cannot move the trial merge.
- `review_cli._node_status` `trial_merge` JSON field and text render line: A1's `handoff status` report (round 3 extended bookkeeping-only reporting).
- Guard in mark `main` and finish `_resolve_main_context`: A2, placed before any write.
- `tests/review_repo_helpers.advance_dev`, `TRIAL_MERGES`, `diverge`: build the three trial-merge cases on the shared review repo.
- `tests/test_git_subprocess.py::test_merge_conflicts_is_in_memory_and_names_conflicted_paths`: clean, conflicted, unknown-ref and non-repository results; the working tree is untouched.
- `tests/test_review_gate.py::test_trial_merge_bookkeeping_is_exact_files_and_whole_directories` (round 1): `roadmap.md` and `roadmap/notes.yaml` are allowed; `roadmap.md.backup`, `workshop/a.py` and a file named `work` block.
- `tests/test_project_layouts.py::test_trial_merge_classifies_conflicts_relative_to_the_project` (round 1, embedded and nested): when nested, a git-root `roadmap/x.json` conflict blocks as `../roadmap/x.json` and `sr/roadmap/registry.yaml` stays bookkeeping; when embedded, both are bookkeeping.
- `tests/test_review_packet.py::test_packet_reports_trial_merge_with_integration_branch` (clean / bookkeeping / code): A1 packet. It is extended (not a new test) to also build with `--base` at the branch tip.
- `review_cli._node_status` `trial_merge` field and its `_render` line (round 3): A1's report of every conflicted file, including a bookkeeping-only conflict, labelled as not blocking (Sol). `_unclaimed` sets `trial_merge: None` so every node has the same JSON keys.
- `tests/test_review_cli.py::test_status_reports_a_trial_merge_conflict` (clean / bookkeeping / code): A1 handoff status. Round 3 renamed it from `..._code_conflict` and extended it to assert the JSON `trial_merge` field and the text line in every case.
- `tests/test_mark_implementation_reviewed_gate.py::test_yes_refuses_while_a_trial_merge_conflicts_on_code` (clean / bookkeeping / code): A2/A3 for mark; registry and HEAD unchanged when refused.
- `tests/test_finish_task_commands.py::test_finish_refuses_while_a_trial_merge_conflicts_on_code` (bookkeeping / code): A2/A3 for finish. A code conflict refuses first; a bookkeeping conflict gets past it to the review gate; HEAD and the tree are unchanged.
- Mocks: none.
- ce4225e merge: nothing added; conflict resolution only.
- d927f96 merge: nothing added; conflict resolution only (trial merge first, then M4.17 escalation/RCA).
