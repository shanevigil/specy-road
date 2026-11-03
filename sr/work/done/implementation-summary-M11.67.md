# Implementation summary: M11.67 — Worker usage prices Cursor runs from the roster's price table

## What changed

Harnesses that report tokens without cost (Cursor `result`, Codex `turn.completed`) get `cost_usd` from the pinned roster profile's `cost_usd_per_mtok` with `cost_is_estimate: true`. The estimate runs once in `Adapter.parse_events` (harness-neutral), not only on Cursor. Lookup is `Profile.for_id` on the argv model (`Profile.api_id` / aliases). Cached input is priced at `cached_input` when that rate is a number, otherwise at the input rate. Nested checkouts resolve via `recorded_project_root(git_root(--workspace / -C))`, else the git worktree. `Cursor.resume` and `Codex.resume` pass `--model` / `-m` the same way their launches do. `specy-road worker usage` already prints `est.` when the flag is set. Top-level CLI help mentions the estimate.

Claude turns that already carry a harness cost are left unchanged (`cost_usd` present → no estimate).

## Touch zones (confirmed)

Added on this branch with `specy-road edit-node M11.67 --add touch_zones=…`:

- `specy_road/worker_adapter_base.py` — `Adapter.parse_events` applies the estimate for every harness
- `specy_road/worker_adapter_codex.py` — `resume` carries `-m` so resumed Codex turns can be priced

Unchanged original zones:

- `specy_road/worker_adapter_parsers.py` — pricing helpers and roster lookup
- `specy_road/worker_adapter_cursor.py` — default launch/resume `--model`; `parse` still leaves cost null
- `specy_road/cli_usage.py` — documents `worker usage` estimates in the command list
- `tests/test_cursor_usage_cost.py` — acceptance coverage

`worker_runner.py` is at the 400-line cap, so the estimate was not added in `_append_usage`.

## Verification

- `specy-road file-limits` — exit 0
- `pytest -q -p no:cacheprovider tests/test_cursor_usage_cost.py tests/test_worker_adapters.py tests/test_worker_resume_permissions.py::test_codex_default_resume_repeats_every_launch_policy_flag tests/test_worker_cli.py::test_usage_events_per_turn_and_the_usage_command` — exit 0

## Added

- `model_from_argv` — read `--model` / `-m` from a launch argv for the profile id during parse
- `worktree_from_argv` — read `--workspace` / `-C` so project root resolves from the worker checkout, not the coordinator cwd
- `project_root_from_worktree` — nested via `recorded_project_root(git_root(wt))`, else the worktree; never `project_root(wt)` or `discover_project_root`
- `_mtok_rate` / `mtok_rates` — parse profile `cost_usd_per_mtok` the same way orchestrate plan reads list prices
- `estimate_usage_cost` — turn USD from token counts with separate cached pricing when a cached rate exists
- `apply_roster_price_estimate` — walk pinned roster profiles and match argv via `Profile.for_id` (api_id / aliases), then estimate when `cost_usd` is still null
- `Adapter.parse_events` estimate branch — one harness-neutral fill when usage has tokens but no cost
- `Cursor.resume` `--model` flag — same as launch, so resumed Cursor turns can be priced
- `Codex.resume` `-m` flag — same as launch, so resumed Codex turns can be priced
- `tests/test_cursor_usage_cost.py` — cached-rate math; recorded Cursor line through `adapter.launch`/`resume` on embedded and nested layouts; unpriced Cursor launch leaves cost null; recorded Codex `turn.completed` through launch and resume with cached input priced at `cached_input`; `worker usage` output shows `est.`
