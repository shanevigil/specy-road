# Implementation summary: M15.33 — refused review record leaves a trace

## Touch zones (confirmed)

- `specy_road/review_rejected.py` (new)
- `specy_road/bundled_scripts/review_cli.py`
- `specy_road/review_run_status.py`
- `tests/`

No other paths were required. `review_record_write._review_record` already calls `cmd_review_record`, so delegate and CLI filing refusals share the same marker logic without editing that module.

## Behaviour

- After `resolve_target` succeeds, `run_review_record` writes `work/reviews/<NODE_ID>/REJECTED-<model>.md` on refusal (except when the model is not on the roster). Front matter carries `commit` and `refused_at`; the stderr refusal text is the body. A successful filing clears the marker.
- `list_reviews` still only loads `REVIEW-*.md`.
- `handoff status` and `review list` show `record refused <age> ago: <first line>` via `review_run_status`; `--json` includes a `refused` map per model with `age` and `reason`. Markers pinned to another commit are hidden.

## Added

- `write_rejected`, `clear_rejected`, `rejected_state`, `ReviewRecordTrace`, `run_review_record` in `review_rejected.py` — marker I/O, age formatting, and the full `review record` command with trace-on-refusal.
- `refused_text`, `refused_by_model`, `extend_handoff_refused`, `print_refused_list` in `review_run_status.py` — display and JSON payload for coordinators.
- `refused` / `extend_handoff_refused` wiring in `review_cli.py` — handoff status and review list output; `cmd_review_record` delegates to `run_review_record`.
- `tests/test_review_rejected_m15_33.py` — A1–A3: loader ignores marker, write/clear, roster miss, handoff/list text+JSON, stale commit, delegated refusal.
