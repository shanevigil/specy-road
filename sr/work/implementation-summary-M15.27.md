# Implementation summary — M15.27

## Summary

Cursor stream-json can emit usage on several lines within one agent turn (`type: usage` mid-turn, `assistant`/`message.usage` when present, and `result`). The adapter now accumulates those lines and combines them once on the terminal `result` so the worker's single usage event matches the full turn. `worker usage` flags long turns whose reported output rate is implausibly low (`possible undercount` in text and JSON).

## Changes

- **`specy_road/worker_adapter_cursor.py`** — Tracks usage-bearing lines per turn; `combine_cursor_turn_usage` sums per-segment counts or takes the last line when outputs are monotonic running totals (with `session_usage` for `turn_usage`); one combined usage on `result`.
- **`specy_road/worker_usage_plausibility.py`** — `MIN_TURN_DURATION_FOR_UNDERCOUNT_SEC` (20 min), `MIN_OUTPUT_TOKENS_PER_MINUTE` (300), and `possible_undercount(events)`.
- **`specy_road/bundled_scripts/worker_cli_render.py`** — Adds `possible_undercount` on attempt/total rows; text lines append `possible undercount`.
- **`tests/fixtures/worker_usage/cursor_multi_segment_turn.json`** — Sanitized multi-segment turn (provenance in file).
- **`tests/test_cursor_usage_segments.py`** — Acceptance tests for summing, plausibility, and CLI shape.
- **`tests/test_worker_adapters.py`**, **`tests/test_cursor_usage_cost.py`** — Reset the shared Cursor adapter segment list where tests parse recorded lines in isolation.
- **`tests/worker_repo_helpers.py`** — Public `run_fake_harness_turn` for fake-harness worker turns (shared with `test_worker_cli`).

### Fixture observations (A1)

From `tests/fixtures/worker_usage/cursor_multi_segment_turn.json` (stream shape from `w-0063.log`, segment usage from the adopter long-turn pattern):

| Line type | Usage? | Count shape |
|-----------|--------|-------------|
| `system` / `init` | no | — |
| `usage` | yes (`usage` object, camelCase) | per-segment |
| `tool_call` | no | — |
| `result` / `success` | yes | per-segment in this fixture (last segment only; 10,136 output tokens); not a running total over earlier segments |

Combined turn output tokens = sum of all four usage lines (7,200 + 8,400 + 6,500 + 10,136 = **32,236**). A single-line short turn (`CURSOR_RESULT`) stays **25** output tokens.

## Verification

```text
python -m pytest -q -p no:cacheprovider tests/test_cursor_usage_segments.py tests/test_worker_adapters.py::test_each_adapter_reports_turn_usage_in_one_shape tests/test_cursor_usage_cost.py tests/test_worker_cli.py::test_usage_events_per_turn_and_the_usage_command
specy-road file-limits
```

## Touch zones (confirmed)

`specy_road/worker_adapter_cursor.py`, `specy_road/worker_usage_plausibility.py`, `specy_road/bundled_scripts/worker_cli_render.py`, `tests/`

## Added

- `combine_cursor_turn_usage` — merges every usage-bearing line of a Cursor turn on `result`.
- `_raw_usage`, `_sum_segments`, `_dominates` — read usage from stream lines and distinguish per-segment sums from running totals.
- `Cursor._usage_segments` / `_track_usage` — per-turn accumulator on the shared adapter instance (cleared on init and after each `result`).
- `worker_usage_plausibility.possible_undercount` — duration vs output-rate heuristic for marking.
- `worker_cli_render._usage_line` — appends the undercount label in text output.
- `tests/fixtures/worker_usage/cursor_multi_segment_turn.json` — sanitized multi-segment acceptance fixture.
- `tests/test_cursor_usage_segments.py` — regression and acceptance coverage for A2/A3.
- `run_fake_harness_turn` in `tests/worker_repo_helpers.py` — public helper for one fake-harness turn through the worker wrapper.
