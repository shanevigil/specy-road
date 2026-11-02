# Implementation summary: M10.2 `normalised-usage-event-in`

## What changed

- `specy_road/schemas/worker-event.schema.json` (A1): new event type `usage`.
  An `if`/`then` on `type: usage` requires `detail`, with all eight fields
  `input_tokens`, `cached_input_tokens`, `output_tokens`, `reasoning_tokens`,
  `cost_usd`, `cost_is_estimate`, `num_turns`, `harness_version` required and
  each nullable (`$defs/usage`). A missing field or a wrong type is refused, so
  absent (`null`) never collapses into 0. One optional extra field,
  `session_cost_usd`, holds Claude Code's running session total.
- `specy_road/worker_adapter_parsers.py`: `usage_fields()` maps a harness's
  `usage` object to the shared shape, and `usage_text()` renders it in one line
  (`?` for a figure not reported). `input_tokens` counts every input token,
  cached ones included, and `cached_input_tokens` is the part read from cache.
  That is how Codex reports them. Claude's `input_tokens` leaves out cache reads
  and writes, so they are added back. Values that are not non-negative numbers
  (the line is model-controlled) become `null`, so a bad line cannot fail schema
  validation and lose the event. `CLAUDE_BARE_TOOLS`, `_names` and
  `_init_detail` moved here unchanged from `worker_adapters.py`, which was at
  its 400-line cap (planning sheet: "move parsing helpers to
  worker_adapter_parsers.py").
- `specy_road/worker_adapters.py` (A2): `Parsed` gains `usage` (the turn's
  normalised figures, or `None`). Existing `detail` shapes are unchanged.
  - Claude Code `result` line (success or error): tokens from `usage`,
    `num_turns`, and `total_cost_usd` as `cost_usd` and `session_cost_usd`, with
    `cost_is_estimate: true`.
  - Codex `turn.completed`: `usage` (`reasoning_output_tokens` → `reasoning_tokens`).
    There is no cost, so the cost fields are `null`.
  - Cursor `result` line: `usage` (snake or camel case) and `num_turns` when the
    line carries them, else `null`. No cost is read, because none is documented.
- `specy_road/worker_runner.py` (A2): `_consume` appends a `usage` event
  (`source: worker`, `authority: worker_suggestion`) right after the event that
  carried the figures. `_append_usage` turns a running session total into this
  turn's cost: `session_cost_usd` minus the previous `usage` event's, or the
  whole total when there is no previous one or it is higher. It fills
  `harness_version` from the latest harness `started` event (Claude's init line
  carries it). A turn whose output carried no usage still gets one all-`null`
  `usage` event in `_finish` before `completion`/`error`. This covers a crash,
  Codex `turn.failed` and `generic`, so every turn end has exactly one. A
  terminated turn gets none.
- `specy_road/bundled_scripts/worker_cli_render.py` (A3): `usage()` /
  `usage_lines()`. Per attempt (worker record) they report the attempt number,
  worker id, harness, last reported version, model, the number of `usage`
  events (`turns`) and each figure summed over the turns that reported it
  (`null` when none did). The node total is computed the same way across
  attempts. `cost_is_estimate` is true if any summed cost was an estimate.
- `specy_road/bundled_scripts/worker_cli.py` (A3): `worker usage W|NODE_ID [--json]`.
  `_records_for()` resolves a worker id to that worker, or a node id to all its
  workers. `timeline` now uses the same helper and still takes the latest one.
- `docs/orchestration-workers.md` (A4): `usage` in the events list, a
  per-harness field table, and the `usage` row in the command table.
- Tests (A4): see Added.

## Touch zones (final)

All nine listed zones were used, and nothing outside them was edited.

Not edited:
- `docs/orchestration-models.md`. The planning sheet's Approach names its
  "prices section", but the file has no prices section (only a "Cost" ranking
  bullet), it is outside the touch zones, and no acceptance item needs it.
- `CHANGELOG.md`. It is outside the touch zones.

## Notes for reviewers

- The sample harness lines in the tests follow each vendor's documented shape.
  They were not captured from a live run in this session. The Claude `result`
  line follows the headless docs (`total_cost_usd`, `num_turns`, `usage` with
  `cache_*_input_tokens`). The Codex line is the `codex exec --json`
  `turn.completed` shape. Cursor's `result` usage is unverified, which is why
  both key cases are read and the no-usage line gives all `null`.
- The Claude cost delta assumes one session per worker. If a human used the
  session between turns (handoff), their spend lands in the next turn's delta.
- Totals add up what was reported. When some turns are `null` for a figure, the
  sum is a lower bound. The docs say so.
- Summed `cost_usd` and the Claude delta are rounded to 6 decimals, which
  removes float noise such as `0.08 - 0.05`.

## Verification

All of these were run in the foreground at commit `b4ac17a`:
- `pytest tests/test_worker_adapters.py tests/test_worker_cli.py` (the brief's verifier): 33 passed.
- The other `tests/test_worker_*.py` files (cli_fixes, faults, m310_reconcile_status, review_round1/2,
  runner_safe_path, state): 80 passed.
- The other tests that import the worker modules or the event log (`test_review_round4_sol*`,
  `test_review_round5`, `test_review_round6_{runner,ops,policy}`, `test_tool_call_guard`, file-limits):
  272 passed.
- `tests/test_cli.py`, `test_context_regressions.py`, `test_enforced_rules_pointers.py`,
  `test_lean_rules.py`, `test_update_specy_road.py`: 97 passed.
- `specy-road file-limits`: OK. `ruff check specy_road tests`: clean.

The full `pytest` suite did not finish within the harness's 20-minute limit for a
background command, and was stopped. It was not run to completion. Before
merging, the coordinator should run the full suite.

## Added

- `worker_adapter_parsers.USAGE_FIELDS`: the eight field names in one place, used by the wrapper (all-null fill) and the schema test.
- `worker_adapter_parsers._num`: guard that turns a non-number, bool or negative value into `null`, so a model-controlled line cannot fail schema validation and drop the event.
- `worker_adapter_parsers.usage_fields`: the per-harness → shared-shape mapping (A2), including the branch that adds Anthropic-style cache buckets back into `input_tokens`.
- `worker_adapter_parsers.usage_text`: one-line rendering shared by the event summary and `worker usage`.
- `worker_adapters.Parsed.usage`: carries the figures from `parse` to the wrapper without changing existing `detail` shapes.
- `worker_runner._append_usage`: writes the `usage` event, with the cumulative → delta conversion (A2) and `harness_version` taken from `started`.
- Branch in `_append_usage`: a total lower than the previous one counts whole. Without it a new session under a custom command would give a negative cost.
- Branch in `_finish`: an all-`null` `usage` event when the turn reported none, for one event per turn end (A2).
- `_consume` return value / `usage_logged` in `run`: tells `_finish` whether the turn already logged usage.
- `worker_cli_render._sum_usage`, `usage`, `usage_lines`: aggregation and text (A3).
- `worker_cli._records_for`, `cmd_usage`, `usage` subparser: the command (A3). `_records_for` replaces the inline lookup in `cmd_timeline`.
- Schema `if`/`then` + `$defs/usage`: A1.
- Mocks: none. Tests use the existing fake-harness scripts.
- Test `test_each_adapter_reports_turn_usage_in_one_shape` (test_worker_adapters.py): A2 per harness from sample lines, plus camel-case Cursor, bad types → `null`, and generic → no usage.
- Test `test_usage_events_per_turn_and_the_usage_command` (test_worker_cli.py): A2 through the wrapper (Claude delta 0.05 → 0.03 across a resume, version from init, Codex tokens, all-`null` event on `turn.failed`) and A3 (`--json`, exact text lines, worker-id target, unknown node exits 1).
- Test `test_usage_event_schema_needs_every_field_nullable_never_missing` (test_worker_cli.py): A1, where nulls and zeros pass and a missing field, wrong type or missing detail fail.
- Helper `_turn` (test_worker_cli.py): runs one fake-harness turn through `worker_runner.run`.
- Updated expectations (not loosened): three event-sequence assertions in test_worker_adapters.py now include the `usage` event that A2 adds at the turn end.
