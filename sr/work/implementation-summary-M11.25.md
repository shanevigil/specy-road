# Implementation summary — M11.25 (`merge-push-disclosure`)

## What changed

Merge-mode finish already called `print_merge_push_notice` before landing; it now predicts **total** commits the integration push will carry and how many are **not** from the finishing feature branch, including when `refs/heads/<integration>` or `refs/remotes/<remote>/<integration>` is absent. `docs/git-workflow.md` documents the notice on the **`merge`** bullet.

## Touch zones (confirmed)

- `specy_road/finish_land_integration.py` — disclosure helpers and notice text
- `docs/git-workflow.md` — merge-mode bullet
- `tests/test_finish_merge_mode.py`, `tests/test_worker_m310_reconcile_status.py` — unit and end-to-end coverage

No edits were required in `specy_road/finish_modes.py` or `specy_road/bundled_scripts/finish_task.py` (they already call `print_merge_push_notice`).

## Acceptance

- **A1:** Notice prints total and not-from-leaf counts; missing local integration or tracking ref still yields counts; docs updated.
- **A2:** `test_finish_merge_prints_push_disclosure_for_unrelated_dev_commit` runs full `finish-this-task` with an extra local `dev` commit and asserts both counts in stdout.

## Verification

- `pytest tests/test_finish_merge_mode.py tests/test_finish_land_check.py tests/test_worker_m310_reconcile_status.py::test_finish_help_and_merge_notice`
- `specy-road file-limits`

## Added

- `_ref_sha` — resolve a ref to a commit sha for range math; reason: shared ref lookup for disclosure helpers.
- `_is_ancestor` — git ancestry check; reason: simulate post-ff integration tip and whether merge adds a commit.
- `_rev_list_count` — `rev-list --count` for a range or single tip; reason: not-from-leaf and total commit counts.
- `_integration_tip_after_ff` — integration tip after landing's ff-only to tracking; reason: base state before feature merge.
- `_feature_merge_adds_commit` — whether landing creates a merge commit; reason: add one to total when the leaf still lands.
- `merge_push_disclosure_counts` — returns `(total, not_from_leaf)`; reason: testable disclosure logic used by the notice.
- `test_merge_push_disclosure_counts_when_local_integration_branch_is_absent` — A1 without local integration ref; reason: regression for missing `refs/heads/<ib>`.
- `test_merge_push_disclosure_counts_when_tracking_ref_is_absent` — A1 without remote-tracking ref; reason: regression for missing `refs/remotes/<remote>/<ib>`.
- `test_finish_merge_prints_push_disclosure_for_unrelated_dev_commit` — A2 end-to-end finish; reason: asserts printed total and not-from-leaf counts on the merge path.
