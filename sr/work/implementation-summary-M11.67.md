# Implementation summary: M11.67 — Worker usage prices Cursor runs from the roster's price table

## What changed

Cursor `result` lines still carry token counts only; on turn end the adapter now looks up the delegated model's pinned profile and fills `cost_usd` from `cost_usd_per_mtok` (cached input at `cached_input` when known, otherwise at the input rate), with `cost_is_estimate: true`. `specy-road worker usage` text output already suffixes `est.` when that flag is set. Top-level CLI help mentions the estimate behaviour.

## Touch zones (confirmed)

- `specy_road/worker_adapter_parsers.py` — pricing helpers and roster lookup
- `specy_road/worker_adapter_cursor.py` — `parse_events` applies estimates after parsing a result line
- `specy_road/cli_usage.py` — documents `worker usage` estimates in the command list
- `tests/test_cursor_usage_cost.py` — acceptance coverage

Codex and other harnesses without harness-reported cost can reuse `apply_roster_price_estimate` from `worker_adapter_parsers`; wiring them was out of this leaf's touch zones (would be `worker_runner._append_usage` or each adapter's `parse_events`).

## Verification

- `specy-road file-limits` — exit 0
- `pytest -q -p no:cacheprovider tests/test_cursor_usage_cost.py tests/test_worker_adapters.py::test_each_adapter_reports_turn_usage_in_one_shape` — exit 0

## Added

- `model_from_argv` — read `--model` / `-m` from a launch argv for roster id during parse
- `worktree_from_argv` — read `--workspace` / `-C` so project root resolves from the worker checkout, not the coordinator cwd
- `_mtok_rate` / `mtok_rates` — parse profile `cost_usd_per_mtok` the same way orchestrate plan reads list prices
- `estimate_usage_cost` — turn USD from token counts with separate cached pricing when a cached rate exists
- `apply_roster_price_estimate` — pinned roster profile lookup plus estimate when `cost_usd` is still null
- `Cursor.parse_events` branch — apply roster estimate on turn-end usage when the line had no cost
- `tests/test_cursor_usage_cost.py` — cached-rate math, recorded Cursor line with priced vs unpriced roster models, and `worker usage` output shows `est.`
