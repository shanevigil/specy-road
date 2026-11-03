# Implementation summary: M11.79 `risk-tiered-review`

## What changed

- **Policy (A1).** `policy.strong_review` is an optional list in `roadmap/orchestration.yaml`. Each item is `{zones: [...], require_one_of: [...]}`: touch-zone paths, directory prefixes or globs, and roster ids. I added it to both copies of the schema (`specy_road/templates/project/schemas/orchestration.schema.json` and `sr/schemas/orchestration.schema.json`) as `$defs/strongReview`. Both lists need at least one entry, and the ids must be unique. `orchestration_config._semantic_error` also refuses a `require_one_of` id that is not in the roster, the same way it treats `substitutions/use`. The key is not added to `DEFAULT_POLICY`; like `ratchet_paths`, it is read with `.get(...)`, so the default is empty.
- **Gate (A1).** At the end of `evaluate_gate`, `GateResult.strong_unmet` is set to the applicable items that have no counted approval (from `result.approvals`) by a model they list. While any item is unmet, `passed` is false, and `problems()` adds one line per item: `strong_review[<n>] (zones: …): the leaf's touch zones meet a strong-review zone; need a counting approval from one of … at this commit, have none`. Handoff status, mark-implementation-reviewed and finish-this-task all print `gate.problems()`, so each of them names the unmet item. Policy comes from the integration branch like the rest. A block, a stale record or an ineligible record never satisfies an item, and neither does a substitute unless its own id is listed. `human_approval_completes` returns true only when every unmet item lists `human`.
- **Zone matching.** An item applies when one of the leaf's touch zones meets one of the item's zones. Zones meet when `finish_implementation_check.zone_matches` (the rule the review packet's `in_zones` uses) matches in either direction, the way the picker's `zone_clash` works. Both the project-root and git-root forms of each zone are tried. In the gate, the leaf's zones are its registry claim's zones plus the node's own. In the plan, they are the node's zones, because ready leaves have no claim.
- **Handoff status rows.** While an item is unmet, each row in `review_eligible.reviewer_eligibility` that can still approve ends with `; would satisfy …` or `; would not satisfy …`. A model whose approval would satisfy an unmet item is no longer excluded as "same family", because a strong approval counts whatever its family.
- **Plan (A2).** For each ready leaf, `orchestrate plan` adds `Assignment.strong_review` (`item`, `require_one_of`, `can_satisfy`), and `--json` carries it too. The text output prints `strong review strong_review[<n>] (zones: …): one approval from …; can satisfy it: …`. `_pick_reviewers` first picks the best-ranked reviewer that can satisfy each item (`_pick_strong`), then fills up to `reviewers_required` as before. Under `reviewers_distinct_families` the fill-up counts distinct families. When no item applies, the picks are unchanged. If no reviewer can satisfy an item, the leaf gets a problem and the plan exits 1.
- **Docs.** `docs/orchestration-review.md` gets a new section, "Strong review for high-risk zones", plus one clause in the paragraph on when the gate passes.

## Touch zones (final list)

These are the listed zones plus **`specy_road/review_strong.py`**. It is a new module because `review_gate.py` is at the 400-line `file-limits` cap. As the planning sheet says, I added it with `specy-road edit-node M11.79 --add touch_zones=specy_road/review_strong.py` (this changed `sr/roadmap/phases/M11__9025e7.json` and the claim row in `sr/roadmap/registry.yaml`, both in the implementation commit). To keep `review_gate.py` at 400 lines, `delta_problem` now reads its zones through `review_strong.touch_zones` (same claim-or-node rule) in place of its inline registry read, and the gate's module docstring paragraph is reflowed with every word kept. The importers flagged outside the zones (`review_cli.py`, `mark_implementation_reviewed.py`, `finish_task.py`) need no change: they already print `gate.problems()`.

## Verification

- `python -m pytest tests/test_strong_review.py -q`: 22 passed.
- `python -m pytest -n auto -q -p no:cacheprovider`: 3553 passed, 2 skipped.
- `specy-road file-limits`: OK.
- `specy-road validate/export --check/digest --check --repo-root tests/fixtures/specy_road_dogfood`: all exit 0.
- `ruff check specy_road tests scripts` reports two C901 findings, both in functions this leaf does not touch: `orchestration_config.load_availability_overlay` and `review_packet_uncommitted_refs.py:82`. Both fail the same way at the base commit. I did not add any noqa.
- `specy-road export --check` for the `sr/` project already reports drift in `sr/roadmap.md` at the base commit (outside the zones), and I left it alone.

## Added

### Helpers (`specy_road/review_strong.py`, new)
- `_clean`: drops blank and non-string zones and strips edge slashes, so a claim's and an item's zones compare the same way.
- `touch_zones`: returns the claim row's zones and the node's zones. The gate's strong check uses both, and `delta_problem` reuses it (claim or node, as before).
- `_forms`: the git-root and project-root forms of a zone, so a zone written from either root meets.
- `zones_meet`: two zones share a path, using `zone_matches` in both directions.
- `applicable_items`: the `(index, item)` pairs a leaf's zones meet. The gate and the plan share it.
- `item_label`: the `strong_review[<n>] (zones: …)` name used in every refusal and plan line.
- `unmet_strong`: the applicable items with no counted approval from their set. The gate's new check.
- `strong_problem`: the gate's refusal text naming the item and its `require_one_of`.
- `human_closes_strong`: stops the interactive human approval from closing a gate whose unmet item does not list `human`.

### Branches and guards
- `GateResult.strong_unmet`, plus `not self.strong_unmet` in `passed` and the problem lines in `problems()`: the A1 refusal.
- `human_approval_completes`: an extra `not human_closes_strong(gate)` early return, so the human cannot close a gate it cannot satisfy.
- `orchestration_config._semantic_error`: refuses a `require_one_of` id not in the roster, so an item can always be satisfied by a real entry.
- `orchestrate_plan._pick_strong` and `Assignment.strong_review`: A2 output, plus picking one reviewer per item first. The fill-up loop's `count()` counts distinct families, because a strong pick may share a family with another pick.
- `assign_leaf(..., prefix="")`: project prefix for zone matching. Existing callers keep the default.
- `review_eligible._meets_strong` and `_strong_text`: the handoff-status rows say who would satisfy an unmet item, and the same-family exclusion is skipped for such a model.
- `orchestrate_cli.render`: one `strong review …` line per item.

### Mocks
- none

### Tests (`tests/test_strong_review.py`, new)
- `test_zones_meet` (7 cases): prefix both ways, glob, near-miss name, unrelated zone, nested-project forms.
- `test_applicable_items_lists_only_the_items_a_zone_meets`: only meeting items, and the empty policy.
- `test_leaf_inside_a_strong_zone_refuses_without_an_approval_from_the_set`: leaf inside a zone with approvals only from outside the set. Count met, gate refuses and names the item.
- `test_an_approval_from_the_set_satisfies_the_item`: an approval from the set passes, even when it shares a family with another.
- `test_a_block_from_the_set_does_not_satisfy_the_item`: a block never counts as the strong approval.
- `test_an_ineligible_approval_from_the_set_does_not_satisfy_the_item`: only a counted approval satisfies.
- `test_leaf_outside_every_strong_zone_needs_only_the_usual_approvals`: leaf outside every zone.
- `test_policy_on_the_feature_branch_alone_does_not_add_the_item`: the policy is read from the integration branch.
- `test_human_completes_only_an_item_that_lists_the_human`: the `human_approval_completes` guard.
- `test_unknown_require_one_of_id_is_a_config_error`: the roster check and the schema's `minItems`.
- `test_handoff_status_names_the_unmet_item_and_who_satisfies_it`: handoff status JSON problems and the eligibility rows.
- `test_mark_implementation_reviewed_refuses_naming_the_item`: `--yes` refuses and names the item.
- `test_plan_shows_the_item_and_picks_a_reviewer_from_the_set`: plan, leaf inside a zone (item, `can_satisfy`, pick, note).
- `test_plan_leaf_outside_the_zone_has_no_item`: plan, leaf outside the zone (no item, picks unchanged).
- `test_plan_item_no_reviewer_can_satisfy_is_unstaffable`: CLI text lines and exit 1.
- `test_plan_json_carries_the_items`: the `--json` output.
