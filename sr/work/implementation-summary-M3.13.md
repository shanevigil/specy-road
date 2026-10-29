# Implementation summary for M3.13

## Summary

Before reviewers run and before finish, the toolkit trial-merges the integration branch into the leaf's branch. It uses `git merge-tree --write-tree`, which merges in memory with no checkout, index or working-tree change.

- **A1:** `review-packet` adds a `Trial merge` line to the packet header. It says whether the branch is up to date, merges cleanly, conflicts only on bookkeeping, or conflicts on code. For a code conflict it names the files and adds a bold **Stop** line telling the executor to merge and resolve before review. `handoff status` (text and `--json`) puts the same conflict message first in the node's `problems`.
- **A2:** `mark-implementation-reviewed` and `finish-this-task` exit 1 while a trial merge of `HEAD` conflicts on any path outside `work/`, `roadmap/`, `planning/`, `roadmap.md` and `roadmap-context.md`. The error names the files and the `git merge <ref>` to run. mark checks before the summary is shown, a human approves, or `REVIEW-human.md` is written. finish checks before the review-gate check and before any status, registry or bookkeeping write.
- **A3:** Tests cover a clean trial merge, a bookkeeping-only conflict (allowed) and a code conflict (refused). They run through the packet, `handoff status`, `mark-implementation-reviewed --yes` and `finish-this-task`, plus the git helper.

The integration ref is the one the rest of the toolkit uses (`finish_implementation_check.base_ref`): the remote-tracking branch as last fetched, else the local branch. Nothing here fetches, so `review-packet` and `handoff status` stay offline and read-only. When git cannot answer (no integration ref, an unknown ref, git older than 2.38 with no `--write-tree`), the packet says "git could not answer" and mark and finish go ahead. This matches the toolkit's existing "say nothing" rule for best-effort git.

## Changes

- `specy_road/git_subprocess.py`: `merge_conflicts(repo_root, ours, theirs)`. It returns the conflicted paths, `[]` when clean, or `None` when git cannot answer. It runs at the repository top level, because `merge-tree` names paths relative to the working directory, so the names are always repository-root names.
- `specy_road/review_gate.py`: `TRIAL_MERGE_BOOKKEEPING`, `is_trial_merge_bookkeeping`, `TrialMerge` (`conflicts`, `code_conflicts`, `problem()`), `trial_merge(repo_root, ref, integration_ref)` and `trial_merge_or_exit(repo_root)`. `trial_merge` rebases every conflicting path to the project with `rebase_to_project`. A path that does not rebase lies outside the project: it always blocks and is shown `../`-relative to the project root. A path that does rebase is bookkeeping only if it is exactly `roadmap.md` or `roadmap-context.md`, or lies below `work/`, `roadmap/` or `planning/`.
- `specy_road/bundled_scripts/review_packet.py`: `_trial_merge_line` in the header.
- `specy_road/bundled_scripts/review_cli.py`: the `handoff status` problems list leads with the trial-merge problem.
- `specy_road/bundled_scripts/mark_implementation_reviewed.py`, `specy_road/bundled_scripts/finish_task.py`: call `trial_merge_or_exit(ROOT)`. In finish it runs after M4.10's `delete_branch_preflight` and before the review check. I had removed finish_task.py's empty `# Git helpers` banner to fit the 400-line cap. M4.10 moved the argument parsing out (349 lines), so the banner is restored and this file's diff against WIP is just the import and the call.
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

## Verification

- After the WIP merge: full `pytest` 2365 passed, 2 skipped, 1 failed. The failure is the inherited M4.10 test above.
- After the merge, the focused tests for both leaves (this leaf's files plus `test_branch_cleanup`, `test_rollup_branch_cleanup` and the `test_finish_*` files): 182 passed, 1 failed (the same inherited test).
- Round 0: full `pytest` 2310 passed, 2 skipped. The full suite was not re-run for round 1.
- Round 1: `pytest tests/test_review_packet.py tests/test_review_cli.py tests/test_mark_implementation_reviewed_gate.py tests/test_finish_task_commands.py tests/test_git_subprocess.py tests/test_review_gate.py tests/test_finish_bookkeeping_wiring.py tests/test_project_layouts.py` → 115 passed.
- Round 1 mutation checks: against d2215f8's `review_gate.py` and `git_subprocess.py`, the `roadmap.md.backup` case fails. Classifying an unrebased path by its raw name, or running `merge-tree` in the project root, fails the nested layout test.
- `specy-road file-limits` → OK. `ruff check specy_road tests` passed before the merge; after it, the only error is the inherited `tests/test_grind_session.py:57`.
- Mutation check: with `merge_conflicts` forced to return `[]`, the six code-conflict and bookkeeping tests fail.

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
- `review_packet._trial_merge_line`: A1's packet report (up to date / clean / bookkeeping-only / code conflict).
- `review_cli._node_status` `merge_problem`: A1's `handoff status` report.
- Guard in mark `main` and finish `_resolve_main_context`: A2, placed before any write.
- `tests/review_repo_helpers.advance_dev`, `TRIAL_MERGES`, `diverge`: build the three trial-merge cases on the shared review repo.
- `tests/test_git_subprocess.py::test_merge_conflicts_is_in_memory_and_names_conflicted_paths`: clean, conflicted, unknown-ref and non-repository results; the working tree is untouched.
- `tests/test_review_gate.py::test_trial_merge_bookkeeping_is_exact_files_and_whole_directories` (round 1): `roadmap.md` and `roadmap/notes.yaml` are allowed; `roadmap.md.backup`, `workshop/a.py` and a file named `work` block.
- `tests/test_project_layouts.py::test_trial_merge_classifies_conflicts_relative_to_the_project` (round 1, embedded and nested): when nested, a git-root `roadmap/x.json` conflict blocks as `../roadmap/x.json` and `sr/roadmap/registry.yaml` stays bookkeeping; when embedded, both are bookkeeping.
- `tests/test_review_packet.py::test_packet_reports_trial_merge_with_integration_branch` (clean / bookkeeping / code): A1 packet.
- `tests/test_review_cli.py::test_status_reports_a_trial_merge_code_conflict` (clean / bookkeeping / code): A1 handoff status.
- `tests/test_mark_implementation_reviewed_gate.py::test_yes_refuses_while_a_trial_merge_conflicts_on_code` (clean / bookkeeping / code): A2/A3 for mark; registry and HEAD unchanged when refused.
- `tests/test_finish_task_commands.py::test_finish_refuses_while_a_trial_merge_conflicts_on_code` (bookkeeping / code): A2/A3 for finish. A code conflict refuses first; a bookkeeping conflict gets past it to the review gate; HEAD and the tree are unchanged.
- Mocks: none.
