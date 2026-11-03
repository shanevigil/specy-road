# Implementation summary: M11.67 — Worker usage prices Cursor runs from the roster's price table

## What changed

Cursor `result` lines still carry token counts only; on turn end the adapter now looks up the pinned profile whose `for_id` matches the argv model (`Profile.api_id` / aliases, the id `_cli_for` puts on `adapter.launch` / `resume`), and fills `cost_usd` from `cost_usd_per_mtok` (cached input at `cached_input` when known, otherwise at the input rate), with `cost_is_estimate: true`. `Cursor.resume` now passes `--model` the same way `launch` does. `specy-road worker usage` text output already suffixes `est.` when that flag is set. Top-level CLI help mentions the estimate behaviour.

## Touch zones (confirmed)

- `specy_road/worker_adapter_parsers.py` — pricing helpers and roster lookup
- `specy_road/worker_adapter_cursor.py` — `parse_events` applies estimates after parsing a result line
- `specy_road/cli_usage.py` — documents `worker usage` estimates in the command list
- `tests/test_cursor_usage_cost.py` — acceptance coverage

Codex and other harnesses without harness-reported cost can reuse `apply_roster_price_estimate` from `worker_adapter_parsers`; wiring them was out of this leaf's touch zones (would be `worker_runner._append_usage` or each adapter's `parse_events`).

## Verification

- `specy-road file-limits` — exit 0
- `pytest -q -p no:cacheprovider tests/test_cursor_usage_cost.py tests/test_worker_adapters.py::test_default_commands_follow_the_documented_cli_flags tests/test_worker_adapters.py::test_each_adapter_reports_turn_usage_in_one_shape` — exit 0

## Added

- `model_from_argv` — read `--model` / `-m` from a launch argv for roster id during parse
- `worktree_from_argv` — read `--workspace` / `-C` so project root resolves from the worker checkout, not the coordinator cwd
- `_mtok_rate` / `mtok_rates` — parse profile `cost_usd_per_mtok` the same way orchestrate plan reads list prices
- `estimate_usage_cost` — turn USD from token counts with separate cached pricing when a cached rate exists
- `apply_roster_price_estimate` — walk pinned roster profiles and match argv via `Profile.for_id` (api_id / aliases), then estimate when `cost_usd` is still null
- `Cursor.parse_events` branch — apply roster estimate on turn-end usage when the line had no cost
- `Cursor.resume` `--model` flag — same `*_model_flag('--model', model)` as launch, so resumed turns can be priced
- `tests/test_cursor_usage_cost.py` — cached-rate math; recorded Cursor line through `adapter.launch(api_id)` and `adapter.resume(api_id)` on a roster whose id is not the profile api_id; unpriced launch leaves cost null; `worker usage` output shows `est.`
