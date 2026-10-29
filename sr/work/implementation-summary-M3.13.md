# Implementation summary for M3.13

## Summary

Before reviewers run and before finish, the toolkit trial-merges the integration branch into the leaf's branch. It uses `git merge-tree --write-tree`, which merges in memory with no checkout, index or working-tree change.

- **A1:** `review-packet` adds a `Trial merge` line to the packet header. It says whether the branch is up to date, merges cleanly, conflicts only on bookkeeping, or conflicts on code. For a code conflict it names the files and adds a bold **Stop** line telling the executor to merge and resolve before review. `handoff status` (text and `--json`) puts the same conflict message first in the node's `problems`.
- **A2:** `mark-implementation-reviewed` and `finish-this-task` exit 1 while a trial merge of `HEAD` conflicts on any path outside `work/`, `roadmap/`, `planning/`, `roadmap.md` and `roadmap-context.md`. The error names the files and the `git merge <ref>` to run. mark checks before the summary is shown, a human approves, or `REVIEW-human.md` is written. finish checks before the review-gate check and before any status, registry or bookkeeping write.
- **A3:** Tests cover a clean trial merge, a bookkeeping-only conflict (allowed) and a code conflict (refused). They run through the packet, `handoff status`, `mark-implementation-reviewed --yes` and `finish-this-task`, plus the git helper.

The integration ref is the one the rest of the toolkit uses (`finish_implementation_check.base_ref`): the remote-tracking branch as last fetched, else the local branch. Nothing here fetches, so `review-packet` and `handoff status` stay offline and read-only. When git cannot answer (no integration ref, an unknown ref, git older than 2.38 with no `--write-tree`), the packet says "git could not answer" and mark and finish go ahead. This matches the toolkit's existing "say nothing" rule for best-effort git.

## Changes

- `specy_road/git_subprocess.py`: `merge_conflicts(repo_root, ours, theirs)`. It returns the conflicted paths (repository-root names), `[]` when clean, or `None` when git cannot answer.
- `specy_road/review_gate.py`: `TRIAL_MERGE_BOOKKEEPING`, `TrialMerge` (`code_conflicts`, `problem()`), `trial_merge(repo_root, ref, integration_ref)` (rebases paths to the project root for the nested layout) and `trial_merge_or_exit(repo_root)`.
- `specy_road/bundled_scripts/review_packet.py`: `_trial_merge_line` in the header.
- `specy_road/bundled_scripts/review_cli.py`: the `handoff status` problems list leads with the trial-merge problem.
- `specy_road/bundled_scripts/mark_implementation_reviewed.py`, `specy_road/bundled_scripts/finish_task.py`: call `trial_merge_or_exit(ROOT)`. finish_task.py was at the 400-line cap, so I removed its empty `# Git helpers` section banner, which had no code under it.
- `docs/orchestration.md` (at the 400-line cap, so I extended the existing "Order:" bullet rather than adding lines) and `docs/dev-workflow.md` (review step 2 and finish step 1).

Final touch zones are the widened list on the claim. Every changed path is inside it: the eight original zones plus `specy_road/bundled_scripts/review_cli.py` and `specy_road/review_gate.py`. Nothing else was needed.

## Verification

- `pytest`: 2310 passed, 2 skipped (full suite, before the final parameter rename).
- After the rename: `pytest tests/test_review_packet.py tests/test_review_cli.py tests/test_mark_implementation_reviewed_gate.py tests/test_finish_task_commands.py tests/test_git_subprocess.py tests/test_review_gate.py tests/test_finish_bookkeeping_wiring.py` → 67 passed.
- `specy-road file-limits` → OK; `ruff check specy_road tests` → all checks passed.
- Mutation check: with `merge_conflicts` forced to return `[]`, the six code-conflict and bookkeeping tests fail.

## Notes for reviewers

- "Allowed" for bookkeeping means only that review and finish do not refuse. The landing still resolves only `roadmap/registry.yaml`, `roadmap.md` and `roadmap-context.md` deterministically. A conflict on a roadmap chunk, a planning sheet or a `work/` file can still stop a merge-mode landing after the bookkeeping commit, as it could before this change. The allowed set follows the coordinator's instruction for this leaf.
- In milestone-rollup finishes the check still runs against the integration branch, not the rollup branch.
- In the nested layout, a conflicted path outside the project keeps its repository-root name and is classified by the same prefixes, the same convention as `review-packet`'s changed-paths section.
- Merging the integration branch after review makes earlier reviews stale, by design: the merge commit becomes the commit under review.

## Added

- `git_subprocess.merge_conflicts`: the one in-memory trial-merge primitive. The guard `code not in (0, 1) or empty tree id` returns `None`, because an unknown ref also exits 1 with nothing on stdout. A test reaches it with `no-such-ref`.
- `review_gate.TRIAL_MERGE_BOOKKEEPING`: the allowed path prefixes, from the coordinator's instruction.
- `review_gate.TrialMerge` / `trial_merge`: shared by the packet, `handoff status`, mark and finish so all four agree. The `None` branch covers no integration ref or git unable to answer, so callers say nothing.
- `review_gate.trial_merge_or_exit`: A2's refusal, shared by mark and finish.
- `review_packet._trial_merge_line`: A1's packet report (up to date / clean / bookkeeping-only / code conflict).
- `review_cli._node_status` `merge_problem`: A1's `handoff status` report.
- Guard in mark `main` and finish `_resolve_main_context`: A2, placed before any write.
- `tests/review_repo_helpers.advance_dev`, `TRIAL_MERGES`, `diverge`: build the three trial-merge cases on the shared review repo.
- `tests/test_git_subprocess.py::test_merge_conflicts_is_in_memory_and_names_conflicted_paths`: clean, conflicted and unknown-ref results; the working tree is untouched.
- `tests/test_review_packet.py::test_packet_reports_trial_merge_with_integration_branch` (clean / bookkeeping / code): A1 packet.
- `tests/test_review_cli.py::test_status_reports_a_trial_merge_code_conflict` (clean / bookkeeping / code): A1 handoff status.
- `tests/test_mark_implementation_reviewed_gate.py::test_yes_refuses_while_a_trial_merge_conflicts_on_code` (clean / bookkeeping / code): A2/A3 for mark; registry and HEAD unchanged when refused.
- `tests/test_finish_task_commands.py::test_finish_refuses_while_a_trial_merge_conflicts_on_code` (bookkeeping / code): A2/A3 for finish. A code conflict refuses first; a bookkeeping conflict gets past it to the review gate; HEAD and the tree are unchanged.
- Mocks: none.
