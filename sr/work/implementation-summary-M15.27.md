# Implementation summary — M15.27

## Summary

Real Composer 2.5 worker logs on this toolkit's grind emit **one** usage-bearing line per agent turn: `type: result` with a `usage` object (`inputTokens`, `outputTokens`, `cacheReadTokens`, `cacheWriteTokens`). The Cursor adapter records that on the worker usage event as before. If a turn ever has more than one usage-bearing line (`type: usage`, `assistant`/`message.usage`, or `result`), token keys are **summed** in `sum_cursor_turn_usage`. Long turns with implausibly low reported output rates get `possible undercount` in text and JSON (A3).

## Changes

- **`specy_road/worker_adapter_cursor.py`** — `_usage_parts` per turn; `sum_cursor_turn_usage` when len > 1; otherwise result usage + `num_turns`.
- **`tests/fixtures/worker_usage/sanitize_cursor_worker_log_turn.py`** — full-turn sanitizer (every line: type, subtype, session_id, usage when present).
- **`tests/fixtures/worker_usage/cursor_multi_segment_turn.json`** — sanitized real longest grind turn (2196 lines, **one** usage-bearing line, 44158 output tokens).
- **`specy_road/worker_usage_plausibility.py`**, **`worker_cli_render.py`**, **`tests/test_cursor_usage_segments.py`** — A3 marking and tests.

### Fixture observations (A1)

| Line type | Carries usage in real grind logs? |
|-----------|-----------------------------------|
| `system` / `init` | no |
| `thinking`, `assistant`, `tool_call`, `user`, … | no (fixture keeps type/subtype/session_id only) |
| `result` / `success` | yes — once per turn |

No per-segment vs running-total distinction appears in observed logs; combining is sum-if-multiple, else the single `result` line.

## Probes

- w-0066 longest turn — 2196 stream lines, **1** usage-bearing line on `result` (`outputTokens` 44158).
- `excerpt_turn` on synthetic init + usage 11 + assistant/message.usage 13 + result 17 — four lines kept, `expected_output_tokens` 41.
- `Cursor.parse` on the same synthetic stream — `output_tokens` 41.
- Real fixture worker test — usage event `output_tokens` 44158.
- `sum_cursor_turn_usage([])` — all null; single part unchanged; `num_turns` 4 preserved on lone `result`.
- WIP merge (M15.13/M8.3) — `worker_cli_helpers`, `worker_lease_helpers`; conflicts resolved with public `make_worker_repo`.

## Verification

```text
python -m pytest -q -p no:cacheprovider tests/test_cursor_usage_segments.py tests/test_worker_adapters.py::test_each_adapter_reports_turn_usage_in_one_shape tests/test_cursor_usage_cost.py tests/test_worker_cli.py::test_usage_events_per_turn_and_the_usage_command
ruff check specy_road tests scripts
specy-road file-limits
```

## Touch zones (confirmed)

`specy_road/worker_adapter_cursor.py`, `specy_road/worker_usage_plausibility.py`, `specy_road/bundled_scripts/worker_cli_render.py`, `tests/`

## Added

- `sum_cursor_turn_usage` — sums token keys when a turn has multiple usage-bearing lines.
- `_usage_parts` / `_track_usage` — per-turn accumulator; cleared on `system`/`init` and after `result`.
- `sanitize_cursor_worker_log_turn.py` — regenerates the committed fixture from a worker log.
- `reset_cursor_adapter_via_init` — test isolation via public init parse.
- `worker_usage_plausibility.possible_undercount` — duration vs output-rate heuristic.
- `tests/test_cursor_usage_segments.py` — sanitizer regression, multi-line sum, real fixture, A3.
