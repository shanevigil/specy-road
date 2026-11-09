# M22.53 — Approvals carry across roadmap, planning and registry changes and code-neutral integration merges

## What changed

`only_planning_or_review_bookkeeping_since` still answers operator decisions with today's rule: this leaf's own planning sheet, its implementation summary and its review files, and never a merge. Review records pass `records=True`. That path carries when every first-parent commit since the approval is project-relative roadmap or planning bookkeeping, or a two-parent merge from the integration history whose non-bookkeeping `--full-index` diff is unchanged.

Paths are judged after the existing project-prefix rebase. `roadmap/**` carries except `roadmap/orchestration.yaml` and `roadmap/git-workflow.yaml`. `planning/**`, `roadmap.md`, `roadmap-context.md`, this leaf's `work/implementation-summary-<id>.md` and `work/reviews/<id>/` carry. A path outside the project, including a `roadmap/` namesake at the git root, does not.

A merge carries only when it has two parents, the second is an ancestor of the ref `policy_source` resolves, and `git diff --full-index` of the non-bookkeeping paths in `merge-base(first, second)..first` equals the same diff of `second..merge`. The walk is `--first-parent`, so commits the merge brought in are not required to be bookkeeping themselves; the diff comparison is what shows the leaf's code did not change. Any other parent count, a second parent off that history, or a git command that fails refuses the whole range.

When the paths would carry, the leaf is read by `node_key` at both commits, so a chunk move still finds it, and its sheet is read from the `planning_dir` recorded at that commit. The carry is refused, and `handoff status` names the reason, when this leaf's acceptance or touch zones differ, when the parsed `## Tier` value differs, when the sheet has no tier value, or when the graph or the sheet cannot be read. A missing tier refuses on every path, including this leaf's own sheet, summary and review files. Another node's acceptance and zones do not refuse the carry.

`count_at_later_commit` now asks for the wider carry and lists a reason string the same way it lists other refusals. Its sibling-head checks are unchanged. `TRIAL_MERGE_BOOKKEEPING` and the packet's bookkeeping marks are unchanged.

## Touch zones

Unchanged: `specy_road/review_bookkeeping.py`, `docs/orchestration-review.md`, `CHANGELOG.md`, `tests/test_sheet_edits_keep_approvals.py`. The reason has to reach `handoff status` from the gate, and operator decisions must keep today's predicate, so the wider path is a flag on the existing function rather than an edit of `review_override.py`.

## Tests

`tests/test_sheet_edits_keep_approvals.py` gains one parameterized test, `test_wider_carry_on_a_nested_project`, on a temporary repo whose project root is a subdirectory. It drives public `handoff status`. Carry rows stay met and say approvals still count. The registry row is also checked at `HEAD`, because a registry-only tip does not move the commit under review. Refusal rows are unmet, the review is listed for re-review, and the acceptance, zone, tier, missing-tier and unreadable graph or sheet rows include the reason. The missing-tier rows cover a wider edit and this leaf's own sheet, summary and review file. The older keep-approval tests install a stable tier before the review, so a later sheet or summary edit still carries. `tests/test_review_hardening.py` still passes, including the unrelated-merge cases.

## Added

### Helpers

- `_leaf_files` — the leaf's summary and review directory, shared by the narrow and wide path checks
- `_is_leaf_file` — those two paths, so the narrow predicate does not drift from the wide one
- `_carries_path` — project-relative roadmap, planning, summary and review paths, excluding the two policy files and anything outside the project
- `_narrow_since` — today's predicate, kept for operator decisions
- `_parents` — a commit's parents, or failure when git cannot answer
- `_on_integration` — the second parent is on the policy-resolved integration history
- `_diff_spec` — one non-bookkeeping pathspec, git-root literal when the path is outside the project
- `_code_diff` — the `--full-index` diff of the non-bookkeeping paths, so the two sides of a merge can be compared as bytes
- `_merge_keeps_code` — a two-parent integration merge whose non-bookkeeping diff is unchanged
- `_ordinary_carries` — one non-merge commit's paths are all bookkeeping
- `_commits_carry` — the first-parent range is bookkeeping or code-neutral merges; any failure refuses the range
- `_node_by_key` — the leaf in the graph at a commit, across chunk moves
- `_sheet_text` — the sheet that commit's node names
- `_contract_problem` — this leaf's acceptance or touch zones differ
- `_tier_problem` — the parsed tier differs, or the sheet has no tier value
- `_evidence_problem` — graph, contract, sheet or tier refuses a carry the paths would allow

### Branches and guards

- `records=False` default — operator decisions keep today's predicate, so a policy commit still ends a decision
- `records=True` in `count_at_later_commit` — only review records use the wider carry
- `isinstance(carried, str)` — a contract or evidence refusal is named on the policy line; a path or merge refusal stays a plain stale review
- `--first-parent` — commits brought in by the merge are not walked; the diff comparison covers them
- `len(parents) != 2` — any other merge shape refuses the range
- failed `rev-list`, `merge-base`, `diff` or `policy_source` — the range does not carry
- a sheet with no parsed tier value refuses the review-record carry on every path, including the leaf's own sheet, summary and review files

### Mocks

- none

### Tests

- `test_wider_carry_on_a_nested_project` — the sheet's rows on a nested project, through `handoff status`
- `_prepare` — nested repo, a second node, and a tier unless the row is a missing-tier case
- `_rel`, `_with_tier`, `_set_field`, `_on_dev`, `_merge` — path, sheet, chunk, integration and merge setup for those rows
- `_other_node`, `_registry`, `_summary`, `_own_sheet`, `_this_acceptance`, `_this_zones`, `_tier_value` — the path and contract rows
- `_policy_workflow`, `_policy_orchestration`, `_namesake` — policy files and a git-root `roadmap/` path
- `_merge_same`, `_merge_code`, `_ours_merge`, `_other_merge` — integration merge, a changed code diff, `-s ours`, and a second parent off the integration history
- `_bad_graph`, `_bad_sheet` — the leaf cannot be resolved by `node_key`, or its sheet cannot be read
- `_review_note` — a file under this leaf's `work/reviews/<id>/`, the narrow missing-tier review-file row

## Probes

The class is a review record whose planning sheet has no parsed `## Tier` value.

- `_tier_problem`'s `narrow` argument: it skipped the refusal when both tiers were missing and the range was only this leaf's sheet, summary or review files. Removed. One rule remains: a differing value is "tier changed"; both missing is "no tier value".
- `_evidence_problem`: it passed `_narrow_since` into that argument. It now calls `_tier_problem` with the two sheets only. A summary-only, sheet-only or review-file-only range with no tier returns the no-tier reason.
- `count_at_later_commit`: it treats `True` as a carry and a string as the named refusal. No second tier check was added. After the change a summary update on a sheet with no tier is a string, so the gate does not keep the approval.
- Operator decisions, the `records` default: still `_narrow_since`, which does not read the tier. `test_the_decision_holds_across_bookkeeping_only` passed: a sheet edit holds the decision and `roadmap/orchestration.yaml` ends it.
- The same commit (`sha == result.commit`): still counts before the carry call. An approval of the commit under review is unchanged.
- Path and merge refusals: they return false before the sheet is read, so a missing tier does not replace them. `tests/test_review_hardening.py` passed, including the unrelated-merge cases, and the policy, namesake, ours and other-merge rows passed.
- A stable tier on the leaf's own sheet or summary: the older keep-approval tests, given that tier before the review, still carry. The nested own-sheet and summary rows with a tier still carry.
- The missing-tier rows (wider edit, own sheet, summary, review file): unmet, and the policy line contains "no tier value".
- `tests/test_sibling_repo_approvals.py`: the same no-tier sheet. Three tests fail. The file is outside the touch zones, so it was not edited. `test_a_record_without_sibling_heads_carries_when_no_sibling_remains` and `test_policy_line_lists_each_approval_and_marks_a_carried_one` expect a summary-only carry. `test_reported_case_sibling_code_and_root_summary_only_does_not_carry` expects the sibling-present reason, which is reached only when the paths would otherwise carry. This is broader than the review's named files; stopped there.
