# Implementation summary — M15.27

## Summary

Cursor stream-json can emit usage on several lines within one agent turn (`type: usage` mid-turn, `assistant`/`message.usage` when present, and `result`). The adapter accumulates each line with a **stream-marked** kind (per-segment vs session running total), combines them once on the terminal `result`, and keeps `num_turns` from that result. `worker usage` flags long turns whose reported output rate is implausibly low (`possible undercount` in text and JSON).

### Combining rule (A2)

| Stream signal | Kind | Token counts |
|---------------|------|--------------|
| `type: usage` (no `subtype: session`) | per-segment | summed |
| `type: usage`, `subtype: session` | session running total | last line wins (`session_usage` set) |
| `assistant` with `message.usage` | per-segment | summed |
| `result` with `usage` | per-segment | summed |
| `result` with `usage.total: true` | session running total | last line wins |

Monotonic output token values alone never select running-total mode.

## Changes

- **`specy_road/worker_adapter_cursor.py`** — `_usage_kind`, `combine_cursor_turn_usage`, `merge_cursor_result_usage`; per-turn `_usage_entries`; cleared on `system`/`init` and after each `result`.
- **`specy_road/worker_usage_plausibility.py`** — undercount constants and `possible_undercount(events)`.
- **`specy_road/bundled_scripts/worker_cli_render.py`** — `possible_undercount` on JSON/text usage rows.
- **`tests/fixtures/worker_usage/cursor_multi_segment_turn.json`** — honest provenance; real `result` field names from w-0056; synthetic mid-turn `type: usage` lines.
- **`tests/test_cursor_usage_segments.py`** — per-segment, session-marked, mixed, `num_turns`, fixture worker path, plausibility.
- **`tests/worker_repo_helpers.py`** — `reset_cursor_adapter_via_init` (public init parse reset).

### Fixture observations (A1)

Scanned Composer 2.5 worker logs under `sr/work/.workers/` (including w-0063.log and w-0056.log, 2026-11-05):

| Line type | Seen in logs? | Usage? | Count shape |
|-----------|---------------|--------|-------------|
| `system` / `init` | yes | no | — |
| `type: usage` | **no** (not in scanned logs) | — | synthetic fixture lines model per-segment |
| `tool_call` | yes | no | — |
| `result` / `success` | yes | yes (`inputTokens`, `outputTokens`, `cacheReadTokens`, `cacheWriteTokens`) | one object per result line (per-segment when combined with other lines) |

Mid-turn `type: usage` lines in the fixture are **not** copied from w-0063 (that log had no JSON usage objects). The terminal `result.usage` object matches the field set observed on w-0056.log result #7 (values sanitized for the multi-segment sum test).

## Probes

- `sr/work/.workers/w-0063.log` and peer Composer logs — no mid-turn `type: usage` with usage objects; only narrative “usage” in thinking deltas.
- `combine_cursor_turn_usage` on segment entries `(100,200,300)` — returns `600`, not `300`.
- `combine_cursor_turn_usage` on `subtype: session` entries `(100,200,300)` — returns `300` with `session_usage`.
- `merge_cursor_result_usage` / `Cursor.parse` on a single `result` with `num_turns: 4` — `num_turns` is `4`, not `None`.
- `reset_cursor_adapter_via_init` — replaces direct `_usage_segments` mutation in cursor usage tests.
- Mixed segment + session entries — session-marked line overrides token keys after segment sum (unit test).

## Verification

```text
python -m pytest -q -p no:cacheprovider tests/test_cursor_usage_segments.py tests/test_worker_adapters.py::test_each_adapter_reports_turn_usage_in_one_shape tests/test_cursor_usage_cost.py tests/test_worker_cli.py::test_usage_events_per_turn_and_the_usage_command
ruff check specy_road tests scripts
specy-road file-limits
```

## Touch zones (confirmed)

`specy_road/worker_adapter_cursor.py`, `specy_road/worker_usage_plausibility.py`, `specy_road/bundled_scripts/worker_cli_render.py`, `tests/`

## Added

- `_usage_kind` — reads segment vs session from stream type/subtype/usage.total only.
- `combine_cursor_turn_usage` — merges `(usage_fields, kind)` entries for a turn.
- `merge_cursor_result_usage` — combine plus `num_turns` from the terminal result line.
- `_usage_entries` / `_track_usage` — per-turn accumulator; cleared on init parse and after result.
- `worker_usage_plausibility.possible_undercount` — duration vs output-rate heuristic.
- `worker_cli_render._usage_line` — appends the undercount label in text output.
- `tests/fixtures/worker_usage/cursor_multi_segment_turn.json` — multi-segment acceptance fixture with documented provenance.
- `tests/test_cursor_usage_segments.py` — regression and acceptance coverage for A2/A3.
- `reset_cursor_adapter_via_init` — test isolation via public `system`/`init` parse.
- `run_fake_harness_turn` — public fake-harness turn helper (prior commit).
