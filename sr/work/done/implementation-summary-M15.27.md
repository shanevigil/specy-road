# Implementation summary — M15.27

## Summary

Real Composer 2.5 worker logs on this toolkit's grind emit **one** usage-bearing line per agent turn: `type: result` with a `usage` object (`inputTokens`, `outputTokens`, `cacheReadTokens`, `cacheWriteTokens`). The Cursor adapter records that on the worker usage event as before. If a turn ever has more than one usage-bearing line (`type: usage`, `assistant`/`message.usage`, or `result`), token keys are **summed** in `sum_cursor_turn_usage`. Long turns with implausibly low reported output rates get `possible undercount` in text and JSON (A3).

## Changes

- **`specy_road/worker_adapter_cursor.py`** — `_usage_parts` per turn; `sum_cursor_turn_usage` when len > 1; otherwise result usage + `num_turns`.
- **`tests/fixtures/worker_usage/sanitize_cursor_worker_log_turn.py`** — full-turn sanitizer (every line: type, subtype, session_id, usage when present).
- **`tests/fixtures/worker_usage/cursor_multi_segment_turn.json`** — sanitized real longest grind turn (2196 lines, **one** usage-bearing line, 44158 output tokens).
- **`specy_road/worker_usage_plausibility.py`**, **`worker_cli_render.py`** (`_usage_total` propagates `possible_undercount` on every summed total), **`tests/test_cursor_usage_segments.py`** — A3 marking and tests.

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
- `_usage_total` / `_combined_node_total` — flagged executor + reviewer JSON/text totals keep `possible_undercount: true`.
- `_usage_total` with unmarked executor + reviewer — combined JSON/text omit the flag.
- Reviewer-only node total (no executor usage events) — no `possible_undercount` on combined total.
- Merge regression class (helper import trapped in embedded harness string) — `test_worker_queue_message.py`: `make_worker_repo` at module scope; `FAKE_SLOW` omits it; `rg 'FAKE.*make_worker_repo'` across `tests/` — no other embedded-script traps.
- Duplicate coverage class (11/13/17 output tokens → 41) — `test_cursor_usage_segments.py`: dropped direct `sum_cursor_turn_usage` test; `test_cursor_parse_sums_when_intermediate_usage_lines_exist` keeps the same inputs via `Cursor.parse`; no other tests repeat that triple.

## Verification

```text
PYTHONDONTWRITEBYTECODE=1 python -m pytest -q -p no:cacheprovider tests/test_cursor_usage_segments.py tests/test_worker_adapters.py tests/test_cursor_usage_cost.py tests/test_worker_cli.py tests/test_review_usage.py tests/test_worker_sync_m15_13.py tests/test_worker_turn_accounting.py tests/test_worker_queue_message.py tests/test_worker_lease_races.py tests/test_worker_max_workers_global.py tests/test_worker_faults.py tests/test_worker_orphans.py tests/test_worker_resume_failed.py tests/test_worker_review_round1.py tests/test_worker_review_round2.py tests/test_m11_27_small_cli_fixes.py tests/test_review_round4_sol.py tests/test_review_round4_sol_b.py tests/test_review_round5.py tests/test_review_round6_ops.py tests/test_review_round6_runner.py tests/test_rework_findings_in_prompt.py
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
- `_usage_total` — single helper for executor totals and executor+reviewer combined totals; carries `possible_undercount` when any input row does.
- `worker_usage_plausibility.possible_undercount` — duration vs output-rate heuristic.
- `tests/test_cursor_usage_segments.py` — sanitizer regression, multi-line sum, real fixture, A3.
