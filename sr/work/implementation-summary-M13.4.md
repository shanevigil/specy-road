# Implementation summary: M13.4

A milestone held by `policy.milestone_full_review` (leaves all Complete, no passing full review) is now visible in `validate` (and so `upgrade`, which calls `validate_at`), `why-blocked` and `list-nodes`.

## Changes

- `specy_road/finish_ancestor_rollup.py`: `held_milestones()` finds milestones whose leaf rollup is Complete, whose authored status is not, and which `milestone_review_hold()` holds; `milestone_review_hold_notice()` formats the reason and the three ways out (review commands, `edit-node <ID> --set status=Complete`, `policy.milestone_full_review: false`). An `UNRESOLVABLE_HOLD` reason gets a one-line notice, matching `demote_pending_milestone_rollups()`, which does not demote it. The review command text is factored into `_review_commands()` so `milestone_review_next_steps()` (output unchanged) and the notice share it.
- `specy_road/bundled_scripts/validate_notices.py` (new): `notice_milestone_review_holds()` prints one notice per held milestone on stdout (so `--strict` does not count it). Called at the end of `validate_at()` in `validate_roadmap.py`.
- `specy_road/bundled_scripts/roadmap_query_cli.py`: `why-blocked` appends the same notice for a held milestone; `--json` gains `review_hold` (reason or `null`). Exit codes unchanged.
- `specy_road/bundled_scripts/roadmap_crud_ops.py`: `list-nodes` ROLLUP shows `In Progress (review hold)` for a held milestone; `--json` rows gain `review_hold: <reason>` at the call site. `--status` filtering still matches the plain rollup. Unresolvable holds are not marked (their rollup stays Complete).
- `docs/orchestration-review.md`: "Milestone full review" shows the notice and the three ways out. Written compactly to stay within the 400-line docs cap.

## Touch zones

Final list: as given; `specy_road/bundled_scripts/validate_notices.py` is the new module (already listed). No change outside the zones.

## Verification

- `python -m pytest -q tests/test_milestone_review_hold_notice.py tests/test_milestone_full_review.py tests/test_why_blocked_plan_holds.py`
- `python -m pytest -n 4 -q`: 4119 passed.
- `specy-road file-limits`: OK. `specy-road validate|export --check|digest --check --repo-root tests/fixtures/specy_road_dogfood`: exit 0, no held milestones in the fixture.

## Probes

(R1: private-name imports from other test modules.)

- `tests/test_milestone_review_hold_notice.py` imports from `tests.test_milestone_full_review`: only `POLICY_OFF`, `set_node_status`, `make_milestone_repo` (no underscore names).
- `tests/test_milestone_full_review.py`: `_set_status` renamed to public `set_node_status`; no remaining `_set_status` symbol or callers in that file.
- All importers of `tests.test_milestone_full_review` in this branch (`test_milestone_review_hold_notice.py`, `test_refusals_name_their_fix.py`): no private-name imports.
- `python scripts/check_test_private_imports.py`: exit 0, 0 new private references.

## Added

- `_review_commands()` (finish_ancestor_rollup.py): one source for the review command text shared by the next-steps line and the notice.
- `held_milestones()` (finish_ancestor_rollup.py): one place that finds held milestones and their reasons for all three commands.
- `milestone_review_hold_notice()` (finish_ancestor_rollup.py): the single formatter A1/A2 ask for.
- Branch in `milestone_review_hold_notice()` for `UNRESOLVABLE_HOLD`: one-line notice so such holds are not invisible, without ways out (rollup not demoted).
- `notice_milestone_review_holds()` (validate_notices.py): validate's printing site, kept out of validate_roadmap.py for its line cap.
- `review_hold` key in why-blocked `--json` and list-nodes `--json`: A2 machine-readable reason.
- Guard in list-nodes skipping `UNRESOLVABLE_HOLD` reasons: their rollup is Complete, so marking them "(review hold)" would be wrong.
- Renamed `_set_status` to public `set_node_status` in tests/test_milestone_full_review.py (callers updated, assertions unchanged): the new test file imports it, and tests must not import underscore names.
- Mocks: none.
- Tests (tests/test_milestone_review_hold_notice.py): validate notice text pinned for a milestone whose leaves are all Complete; why-blocked text and JSON; list-nodes text mark and JSON field; no notice with policy off or with the milestone recorded Complete; one-line unresolvable notice.
