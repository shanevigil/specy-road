# Implementation summary: M11.27 — Small CLI fixes from field use

## What changed

- **A1:** `specy-road prompt` prints `Wrote <path>` on stderr so stdout stays prompt-only when redirected.
- **A2:** Ancestor rollup during `finish-this-task` skips post-chunk validation (`validate=False` on `edit_node_set_pairs` / `write_node_update`) so the later `validate` subprocess does not repeat the same warnings.
- **A3:** `validate` lists every node missing `planning_dir` and prints `fix: specy-road scaffold-planning <ID>` for each before exiting.
- **A4:** Worker completion on exit 0 distinguishes a fresh invalid READY (`READY file invalid: <reason>`, matching handoff status errors) from no READY (`READY file missing`). Logic lives in `specy_road/worker_runner_ready.py` to keep `worker_runner.py` under the file cap.
- **A5:** `worker list` and `worker sync` include `worktree=<path>` on each worker line (`worker show` already printed worktree).

## Touch zones (confirmed)

Original PM list plus files required for A2/A3 and the runner cap split:

- `specy_road/bundled_scripts/session_cli.py` — unchanged (no acceptance item)
- `specy_road/bundled_scripts/worker_cli.py`
- `specy_road/bundled_scripts/worker_cli_render.py`
- `specy_road/worker_adapters.py` — unchanged
- `specy_road/worker_ops.py` — unchanged
- `specy_road/bundled_scripts/role_prompt.py`
- `specy_road/worker_runner.py`
- `specy_road/worker_runner_ready.py` (new; cap split)
- `specy_road/bundled_scripts/validate_roadmap_checks.py` (A3)
- `specy_road/bundled_scripts/roadmap_chunk_router.py` (A2 `validate=` on chunk write)
- `specy_road/bundled_scripts/roadmap_crud_ops.py` (A2)
- `specy_road/finish_ancestor_rollup.py` (A2)
- `tests/`

## Verification

- `pytest tests/test_m11_27_small_cli_fixes.py`
- `specy-road file-limits`

## Added

- `specy_road/worker_runner_ready.py` — READY fingerprint, invalid-vs-missing completion text, and `fresh_ready` extracted from the runner for the 400-line cap.
- `all_ready_fingerprints` / `fresh_invalid_ready_reason` / `completion_summary` / `fresh_ready` in that module — A4 completion messaging shared with handoff error text.
- `validate=False` on `write_node_update` and `edit_node_set_pairs` — lets finish rollup defer validation to the single subprocess pass (A2).
- `validate=False` in `finish_ancestor_rollup._set_complete` — ancestor status writes no longer trigger a full validate before finish's own run (A2).
- `worktree=` in `_line` and `sync_worker_header`; sync passes `rec.worktree` into the header dict — A5 coordinator visibility.
- Per-node `fix: specy-road scaffold-planning <ID>` lines in `validate_required_planning_dirs` — A3.
- `tests/test_m11_27_small_cli_fixes.py` — acceptance tests for A1–A5.
