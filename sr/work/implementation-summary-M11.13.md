# Implementation summary: M11.13 — milestone full review

A milestone (any node with leaf children) now gets one full review of its combined change before it is marked Complete, under `policy.milestone_full_review` (default on).

## Walkthrough

- **Policy** (`orchestration_config.py`, both `orchestration.schema.json` copies): `milestone_full_review`, boolean, default true, read from the integration branch like the rest of the policy.
- **Target** (`review_target.py`): a milestone has no registry claim, so `resolve_target` gives it the integration tip (remote-tracking ref first, else local; `--ref` overrides) as the commit under review and, as base, the first parent of the oldest `chore(rm-<codename>): register as in-progress` commit of any leaf under it that the tip reaches (`milestone_review_base`; the common ancestor of the branch points when several leaves registered). `ReviewTarget.milestone` marks it. The shared display helpers live here too (`milestone_status`, `milestone_packet_lines`, `MILESTONE_SUMMARY`, `milestone_base_or_exit`) so the packet and the CLI agree and neither bundled script grows past the file limit.
- **Hold** (`finish_ancestor_rollup.py`): `rolled_up_stale_ancestor_ids` takes a `held` callback and stops the walk at a held ancestor; `milestone_review_hold` returns the reason when the node is a milestone, the review gate is on, the policy is on and the gate at the milestone's target is not passed (an unresolvable target holds too). `complete_rolled_up_ancestors` prints `[hold] …` with the next commands and opens `work/reviews/<MILESTONE_ID>/` so `handoff status` lists the milestone. `complete_reviewed_milestone` is the release: it sets the milestone Complete (refusing while a leaf is open) and then the stale ancestors above it.
- **Packet** (`review_packet.py`): a milestone header line names the leaves covered, the base line says it is the first leaf's branch point, the summary section says a milestone has none, and a milestone with no reachable leaf registration exits with a `--base` hint. `_policy_line` and `_trial_merge_line` moved to `review_gate.py` as `policy_source_line` and `trial_merge_lines`, unchanged, to keep the file under 400 lines.
- **CLI** (`review_cli.py`): `handoff status` shows `awaiting_full_review` (exit 1) for a finished milestone whose gate is not met, `approved` with the release command when it is, and `complete_no_claim` once Complete; the hint is appended to the node's problems. `review list` prints the same next step under the gate line. The state computation in `_node_status` was folded into two lines to make room; behaviour for leaves is unchanged.
- **Release** (`mark_implementation_reviewed.py`): an optional positional `node_id` closes a milestone: it must be a milestone with every leaf Complete; the gate (interactive human approval or `--yes`, as for a leaf) is evaluated at the milestone's target commit; then the roadmap chunk is updated, `validate`/`export`/`digest` regenerate the committed files, and one commit `roadmap: <ID> full review approved; status -> Complete` carries the `Reviewed-by` trailers.
- **Docs** (`docs/orchestration-review.md`): a "Milestone full review" section and an `awaiting_full_review` row in the state table.

## Touch zones (final)

As listed on the node after the coordinator widened them: `specy_road/bundled_scripts/review_packet.py`, `specy_road/review_gate.py`, `specy_road/finish_ancestor_rollup.py`, `specy_road/templates/project/schemas/orchestration.schema.json`, `sr/schemas/`, `docs/orchestration-review.md`, `tests/`, `specy_road/review_target.py`, `specy_road/bundled_scripts/review_cli.py`, `specy_road/bundled_scripts/mark_implementation_reviewed.py`, `specy_road/orchestration_config.py`. Nothing outside them changed.

## Notes for the reviewers

- Readers that compute the rollup from leaves (`roadmap.md`, brief, PM GUI) still show a held milestone as Complete; the authored status, `list-nodes` and `handoff status` show the hold. Changing the rollup computation was out of scope.
- A milestone review record needs an empty `acceptance` map: a milestone has no acceptance ids, and the gate rejects unknown ids as for a leaf.
- The hold creates the hand-off directory in the main checkout; it is gitignored like every `work/reviews/` directory.
- `review_cli.py` and `orchestration_config.py` are also edited by M11.7 and M11.8; the edits here are an import, three lines in `_node_status`, two in `cmd_review_list`, the first check of `_check_record`, and one dict entry.

## Review round 2 (Sol's block, 2026-11-02)

1. **Held until the last leaf has landed.** `resolve_target` now records, for a milestone, the leaves whose chunk at the commit under review does not say Complete (`unfinished_leaves_at` reads each leaf's chunk with `git show <commit>:./<chunk>`; an unreadable chunk counts as unfinished). `milestone_review_hold` holds while any such leaf exists, before it looks at the gate, so an approval recorded against a pre-landing tip never releases the milestone; after the merge that approval is stale anyway. Regression test: approve after alpha, finish beta on its branch, hold; merge, still held; fresh review, released.
2. **Closure requires the integration checkout at the gated commit.** `milestone_close_problem` (review_target) refuses when a leaf is open at the target, when the checked-out branch is not the configured integration branch, or when `HEAD` is not the commit under review (the remote-tracking tip when there is one). `_close_milestone` runs it right after resolving the target, before the gate, so nothing is read, prompted or written first. Tests: wrong branch; local `dev` one commit ahead of `origin/dev` with the record bound to the remote tip.
3. **Unfinished milestones are not `awaiting_full_review`.** `milestone_status` reports `leaves_open` with the leaves named; `review-packet` and `review record` refuse for such a milestone with the same message (`milestone_packet_or_exit`, `milestone_open_problem`). Docs updated with the state, the landed-tip rule and the checkout requirement.

Merged `origin/WIP/improvements-0-3-1` first (clean; it did not touch these files).

## Verification

- `python -m pytest -q tests/test_milestone_full_review.py tests/test_finish_ancestor_rollup.py tests/test_review_packet.py tests/test_review_cli.py tests/test_review_gate.py tests/test_mark_implementation_reviewed_gate.py tests/test_orchestration_config.py -p no:cacheprovider` → 107 passed.
- `specy-road file-limits` → OK.
- `ruff check specy_road tests/test_milestone_full_review.py` → clean.

## Added

- `DEFAULT_POLICY["milestone_full_review"] = True` and the matching schema property (template and `sr/schemas/`): the policy switch, A1/A2.
- `ReviewTarget.milestone` field and `leaf_ids` property: lets every command know it is looking at a milestone and which leaves it covers.
- `leaf_descendants(nodes, node_id)`, `is_milestone(nodes, node_id)` (review_target): the reviewed unit is a node with leaf children.
- `REGISTER_SUBJECT`, `milestone_review_base(repo_root, nodes, node_id, tip)` (review_target): the packet range start, A1.
- Milestone branch in `resolve_target`: integration tip as ref/commit, `milestone_review_base` as base, error when the integration branch is unreachable.
- `MILESTONE_SUMMARY`, `milestone_status(t, state)`, `milestone_packet_lines(t)`, `milestone_packet_or_exit(t)` (review_target): shared display, the open-leaves and `--base` refusals, A2.
- `ReviewTarget.unfinished_leaves` field and `unfinished_leaves_at(repo_root, nodes, node_id, commit)` (review_target): leaf status read at the commit under review, round 2 change 1.
- `milestone_open_problem(t)` (review_target): the one message for an unfinished milestone, used by the CLI state, the packet and `review record`, round 2 change 3.
- `milestone_close_problem(repo_root, t)` (review_target) and its call in `_close_milestone`: open leaves, wrong branch, divergent `HEAD`, round 2 change 2.
- Open-leaves guard in `milestone_review_hold` before the gate: round 2 change 1.
- `leaves_open` state in `milestone_status` and the record refusal in `_check_record`: round 2 change 3.
- `held` parameter on `rolled_up_stale_ancestor_ids`: the hold point, ends the walk at a held milestone so ancestors above it wait, A1.
- `milestone_review_hold(repo_root, nodes, node_id)`, `milestone_review_next_steps(node_id)`, `_print_hold(repo_root, nodes)` (finish_ancestor_rollup): decide, explain and open the hand-off directory for a hold.
- `_set_complete(root, node_id)` (finish_ancestor_rollup): the status write extracted from the old loop so the release can reuse it; same messages as before.
- `complete_reviewed_milestone(repo_root, node_id)` (finish_ancestor_rollup): the release, A1/A3.
- `policy_source_line(root)`, `trial_merge_lines(root, ref, integration_ref)` (review_gate): moved from review_packet unchanged (file limit).
- `commit` keyword on `_gate_or_human_approval` and the `node_id` positional plus `_close_milestone(args, node_id)` (mark_implementation_reviewed): the approval path for a milestone, A1/A3.
- `milestone_status` calls in `_node_status` and `cmd_review_list` (review_cli): A2.
- Docs section "Milestone full review" and the `awaiting_full_review` table row: A2.
- Tests, `tests/test_milestone_full_review.py` (one file, a git fixture with phase `M2` over leaves `M2.1`/`M2.2` landed pickup-style):
  - `test_milestone_target_is_the_integration_tip_from_the_first_leaf_branch_point`: target and range, A1.
  - `test_milestone_packet_covers_both_leaves_and_base_overrides`: packet header, both leaves' diff, `--base`, A1/A3.
  - `test_milestone_packet_without_a_registration_commit_needs_base`: the `--base` refusal.
  - `test_rollup_is_held_until_the_milestone_full_review_passes`: rollup held, then released by a record, A1/A3.
  - `test_policy_off_restores_the_plain_rollup`: A2/A3.
  - `test_handoff_status_and_review_list_show_a_milestone_awaiting_its_full_review`: A2.
  - `test_approval_through_mark_implementation_reviewed_releases_the_rollup`: `--yes` refuses without a record, then closes with trailers and regenerated files, A3.
  - `test_mark_implementation_reviewed_refuses_a_leaf_id_and_an_open_milestone`: guard rails.
  - `test_an_approval_before_the_last_leaf_lands_never_releases_the_hold`: Sol's regression, round 2 change 1.
  - `test_an_unfinished_milestone_is_not_awaiting_its_full_review`: `leaves_open`, packet and record refusals, round 2 change 3.
  - `test_close_refuses_on_the_wrong_branch`, `test_close_refuses_a_divergent_integration_tip`: round 2 change 2.
  - Helpers `_branch_leaf` / `_merge_leaf` split out of `_land_leaf` so a leaf can be finished before it lands.
- Mocks: none.
