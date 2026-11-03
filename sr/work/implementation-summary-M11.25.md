# Implementation summary — M11.25 (`merge-push-disclosure`)

## What changed

Merge-mode finish already called `print_merge_push_notice` before landing; it now predicts **total** commits the integration push will carry and how many are **not** from the finishing feature branch, including when `refs/heads/<integration>` or `refs/remotes/<remote>/<integration>` is absent. `docs/git-workflow.md` documents the notice on the **`merge`** bullet.

`total` is the union of commits newly reachable from the post-ff integration tip and the feature branch relative to the remote-tracking baseline, plus the landing merge commit when one will be created. Shared ancestry is counted once. With no tracking ref, `_rev_list_count(..., exclude=None)` counts the full reachable set.

## Touch zones (confirmed)

- `specy_road/finish_land_integration.py` — disclosure helpers and notice text
- `docs/git-workflow.md` — merge-mode bullet
- `tests/test_finish_merge_mode.py`, `tests/test_worker_m310_reconcile_status.py` — unit and end-to-end coverage

No edits were required in `specy_road/finish_modes.py` or `specy_road/bundled_scripts/finish_task.py` (they already call `print_merge_push_notice`).

## Acceptance

- **A1:** Notice prints total and not-from-leaf counts; missing local integration or tracking ref still yields counts; docs updated.
- **A2:** `test_finish_merge_prints_push_disclosure_for_unrelated_dev_commit` runs `python -m specy_road.cli finish-this-task` with an extra local `dev` commit and asserts the printed total equals `rev-list --count` on the remote integration ref before vs after.

## Sol required changes (REVIEW-gpt-6.1-sol.md)

- **Count all newly reachable commits, including feature-only and the merge commit, without double-counting shared ancestry.** Commit `94b99596` (`merge_push_disclosure_counts` unions both tips via `rev-list --count A B --not baseline`). Tests: `test_finish_merge_prints_push_disclosure_for_unrelated_dev_commit`, `test_finish_help_and_merge_notice`.
- **Extend the end-to-end test to compare the printed total against remote integration history, and correct undercount expectations.** Commit `94b99596`. Test: `test_finish_merge_prints_push_disclosure_for_unrelated_dev_commit` (public CLI; `before..dev` on the bare remote). Also corrected oracles in `test_merge_push_disclosure_counts_when_local_integration_branch_is_absent`, `test_merge_push_disclosure_counts_when_tracking_ref_is_absent`, and `test_finish_help_and_merge_notice`.
- **Remove the unreachable None-base arm of `_rev_list_count`, or use it for missing tracking.** Commit `94b99596`. `_rev_list_count(..., exclude=None)` is the missing-tracking path (no `--not`). Test: `test_merge_push_disclosure_counts_when_tracking_ref_is_absent`.

## Verification

- `pytest tests/test_finish_merge_mode.py tests/test_finish_land_check.py tests/test_worker_m310_reconcile_status.py::test_finish_help_and_merge_notice`
- `specy-road file-limits`

## Added

- `_ref_sha` — resolve a ref to a commit sha for range math; reason: shared ref lookup for disclosure helpers.
- `_is_ancestor` — git ancestry check; reason: simulate post-ff integration tip and whether merge adds a commit.
- `_rev_list_count` — `rev-list --count` over tips, `exclude=None` for the full reachable set; reason: union counts and missing-tracking baseline.
- `_integration_tip_after_ff` — integration tip after landing's ff-only to tracking; reason: base state before feature merge.
- `_feature_merge_adds_commit` — whether landing creates a merge commit; reason: add one to total when the leaf still lands.
- `merge_push_disclosure_counts` — returns `(total, not_from_leaf)`; reason: testable disclosure logic used by the notice.
- `_merge_mode_finish_repo` — real merge-mode repo with a bare origin; reason: A2 fixture.
- `_finish_cli` — `python -m specy_road.cli finish-this-task`; reason: A2 through the public CLI, no private patches.
- `_push_disclosure` — parse printed total and not-from-leaf counts; reason: shared oracle for notice tests.
- `test_merge_push_disclosure_counts_when_local_integration_branch_is_absent` — A1 without local integration ref; reason: regression for missing `refs/heads/<ib>`.
- `test_merge_push_disclosure_counts_when_tracking_ref_is_absent` — A1 without remote-tracking ref; reason: exercises `exclude=None` full reachable count.
- `test_finish_merge_prints_push_disclosure_for_unrelated_dev_commit` — A2 end-to-end finish CLI; reason: printed total vs remote `before..dev`, not-from-leaf is the unrelated commit.
