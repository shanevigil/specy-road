# Implementation summary: M11.27 — Small CLI fixes from field use

## What changed

- **A1:** `specy-road prompt` prints `Wrote <path>` on stderr so stdout stays prompt-only when redirected.
- **A2:** Ancestor rollup writes Complete into the chunk the same way finish patches the leaf, so it does not run a nested validate; finish's later validate/export/digest is the one pass.
- **A3:** `validate` lists every node missing `planning_dir` and prints `fix: specy-road scaffold-planning <ID>` for each before exiting.
- **A4:** Worker completion on exit 0 distinguishes a fresh invalid READY (`READY file invalid: <reason>`, matching handoff status errors) from no READY (`READY file missing`). Logic lives in `specy_road/worker_runner_ready.py` to keep `worker_runner.py` under the file cap.
- **A5:** `worker list` and `worker sync` include `worktree=<path>` on each worker line (`worker show` already printed worktree).

`roadmap_chunk_router.py` and `roadmap_crud_ops.py` were reverted: A2 does not need a `validate=` flag on CRUD.

## Kept out-of-zone files

- `specy_road/bundled_scripts/validate_roadmap_checks.py` — A3 is this function; missing-`planning_dir` listing and the `scaffold-planning` fix line live here.
- `specy_road/finish_ancestor_rollup.py` — A2: nested `edit-node` validate during ancestor rollup was the extra warning pass; the chunk write must skip it.
- `specy_road/worker_runner_ready.py` — A4: new module so `worker_runner.py` stays under the 400-line cap (executor rule for a cap split).

## Touch zones (confirmed)

Original PM list plus the three kept files above (`edit-node --add`):

- `specy_road/bundled_scripts/session_cli.py` — unchanged (no acceptance item)
- `specy_road/bundled_scripts/worker_cli.py`
- `specy_road/bundled_scripts/worker_cli_render.py`
- `specy_road/worker_adapters.py` — unchanged
- `specy_road/worker_ops.py` — unchanged
- `specy_road/bundled_scripts/role_prompt.py`
- `specy_road/worker_runner.py`
- `specy_road/worker_runner_ready.py`
- `specy_road/bundled_scripts/validate_roadmap_checks.py`
- `specy_road/finish_ancestor_rollup.py`
- `tests/`

## Verification

- `pytest tests/test_m11_27_small_cli_fixes.py`
- `specy-road file-limits`

## Added

- `specy_road/worker_runner_ready.py` — invalid-vs-missing completion text and `fresh_ready` extracted from the runner for the 400-line cap.
- `all_ready_fingerprints` / `fresh_invalid_ready_reason` / `completion_summary` / `fresh_ready` in that module — A4 completion messaging shared with handoff error text.
- `fresh_invalid_ready_reason` catches `Exception` and `SystemExit` from `load_roadmap`/`acceptance_ids` and uses `next(..., None)` — a broken or nodeless graph cannot abort `_finish`; the summary falls back to `READY file missing`.
- `all_ready_fingerprints` reuses `worker_process._fingerprint` instead of a duplicate.
- `_set_complete` writes the ancestor chunk directly (no `edit_node_set_pairs`) — A2, so finish's validate is the only pass.
- `worktree=` in `_line` and `sync_worker_header`; sync passes `rec.worktree` into the header dict — A5 coordinator visibility.
- Per-node `fix: specy-road scaffold-planning <ID>` lines in `validate_required_planning_dirs` — A3.
- `tests/test_m11_27_small_cli_fixes.py` — acceptance tests for A1–A5.
- A2 fixture writes `policy.milestone_full_review: false` and asserts a non-empty `complete_rolled_up_ancestors` result before counting the acceptance warning (review finding: the hold skipped the ancestor write).
- A4 test compares the completion reason to `list_ready(...).errors` instead of `review_cli._node_status`.
- `test_exit_zero_with_a_broken_roadmap_still_completes_idle` — an exit-0 turn with unparseable `manifest.json` still records a completion and leaves the worker idle.
