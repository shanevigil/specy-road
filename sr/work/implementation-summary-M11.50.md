# M11.50 — finish keeps a committed implementation summary in history

## Summary

When `finish-this-task` cleans up session files, a **tracked** `work/implementation-summary-<NODE_ID>.md` is now moved to `work/done/implementation-summary-<NODE_ID>.md` and both sides are staged in the bookkeeping commit. Brief and prompt are still removed. Untracked summaries continue to be copied under `work/reviews/<NODE_ID>/` before removal.

## Changes

- `specy_road/finish_work_artifacts.py`: `archived_implementation_summary_rel`, `_archive_tracked_summary`, and `cleanup_work_artifacts` skip deleting a tracked summary in favour of the archive move.
- `tests/test_finish_work_cleanup.py`: extended tracked-path cleanup test; assertions on the worker→finish integration test; new `test_finish_archives_committed_summary_in_bookkeeping_commit` for A1.
- `docs/git-workflow.md` and `docs/dev-workflow.md`: describe `work/done/` as the post-finish home for committed summaries.

## Verification

- `pytest tests/test_finish_work_cleanup.py tests/test_finish_bookkeeping_wiring.py -q`
- `specy-road file-limits`

## Touch zones (confirmed)

`specy_road/finish_work_artifacts.py`, `specy_road/bundled_scripts/finish_task.py` (no code change — existing `git add` of cleanup paths already stages archive additions), `tests/`, `docs/git-workflow.md`, `docs/dev-workflow.md`.

## Added

- `archived_implementation_summary_rel` — stable archive path for a node's summary.
- `_archive_tracked_summary` — filesystem move plus return values for bookkeeping `git add`.
- Branch in `cleanup_work_artifacts` — skip `remove_work_file` on the summary when archive ran.
- `test_finish_archives_committed_summary_in_bookkeeping_commit` — A1 through public `finish-this-task`.
- Extended `test_cleanup_work_artifacts_tracked_paths_returned` — archive move and content at `work/done/`.
- Extended `test_an_opted_in_completed_worker_goes_through_review_to_finish` — archive visible in finish commit.
