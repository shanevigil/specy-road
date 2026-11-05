# Implementation summary — M15.27

## Summary

Cursor stream-json usage is combined once on the terminal `result` for the worker's single usage event. Rules follow what Composer 2.5 worker logs on this toolkit's grind actually show, plus explicit stream markers when several usage-bearing lines appear in one turn. `worker usage` flags long turns whose reported output rate is implausibly low.

### Combining rule (A2)

Observed on real Composer 2.5 grind logs (longest turn excerpt committed as the fixture): **one** `result` / `success` line per agent turn carries `usage` (`inputTokens`, `outputTokens`, `cacheReadTokens`, `cacheWriteTokens`); no mid-turn `type: usage` lines in those logs.

When multiple usage-bearing lines exist in one turn:

| Stream signal | Kind | Turn usage |
|---------------|------|------------|
| `type: usage` (not `subtype: session`), `assistant` / `message.usage`, `result` / `usage` without `total: true` | per-segment | sum token keys |
| `type: usage`, `subtype: session`, or `result` / `usage` with `total: true` | session total | **last** session line only; omitted keys stay null (no merge with segment sums) |

Monotonic token values never imply a running total.

## Changes

- **`tests/fixtures/worker_usage/sanitize_cursor_worker_log_turn.py`** — builds sanitized turn fixtures from a worker log.
- **`tests/fixtures/worker_usage/cursor_multi_segment_turn.json`** — sanitized excerpt of the longest Composer 2.5 turn (real `result.usage` numbers).
- **`specy_road/worker_adapter_cursor.py`** — session lines replace the turn total entirely; docstring matches observed grind shape.
- **`tests/test_cursor_usage_segments.py`** — fixture from real excerpt; edge-case combine/parse tests; worker path.

## Probes

- Longest Composer 2.5 turns in local worker logs (w-0052, w-0053, w-0066) — each turn has a single `result.usage`; no mid-turn `type: usage` with usage objects.
- `sanitize_cursor_worker_log_turn.py` on w-0066 — `expected_output_tokens` 44158 from real `outputTokens`.
- `combine_cursor_turn_usage` with segment + session entries — output and `cached_input_tokens` taken only from session line (null stays null).
- `Cursor.parse` assistant `message.usage` + `result` with `usage.total: true` — `output_tokens` 7, `cached_input_tokens` None (Grok probe).
- Per-segment-only entries `(100,200,300)` — still sum to 600.
- `reset_cursor_adapter_via_init` — no `_usage_segments` test mutation.

## Verification

```text
python -m pytest -q -p no:cacheprovider tests/test_cursor_usage_segments.py tests/test_worker_adapters.py::test_each_adapter_reports_turn_usage_in_one_shape tests/test_cursor_usage_cost.py tests/test_worker_cli.py::test_usage_events_per_turn_and_the_usage_command
ruff check specy_road tests scripts
specy-road file-limits
```

## Touch zones (confirmed)

`specy_road/worker_adapter_cursor.py`, `specy_road/worker_usage_plausibility.py`, `specy_road/bundled_scripts/worker_cli_render.py`, `tests/`

## Added

- `sanitize_cursor_worker_log_turn.py` — maintainer script to regenerate the sanitized fixture from a worker log.
- `_usage_kind` / `combine_cursor_turn_usage` / `merge_cursor_result_usage` — stream-marked segment vs session combine.
- `reset_cursor_adapter_via_init` — test isolation via `system`/`init` parse.
- `tests/fixtures/worker_usage/cursor_multi_segment_turn.json` — real long-turn excerpt (44158 output tokens on `result`).
- `tests/test_cursor_usage_segments.py` — fixture, edge cases, plausibility, worker integration.
