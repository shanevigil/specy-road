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

## Review round 1 (gpt-6.1-sol, block): fixes

- **R1:** a harness that cannot start (`OSError` → exit 127) now also ends the
  turn with one all-`null` `usage` event. It is written just before the
  existing `error` event; the error and the `failed` state are unchanged.
  `test_run_reports_a_missing_binary_as_failed` asserts it.
- **R2:** `usage_fields` now adds a reported cache-creation (write) bucket to
  `input_tokens` even when no cache reads are reported. `cached_input_tokens`
  stays `null` when reads are unreported. The adapter test covers
  `{input_tokens: 12, cache_creation_input_tokens: 3000}` → `3012 / null`.
- **R3:** the tests now use recorded, sanitized turn-end lines, in
  `tests/fixtures/worker_usage/turn_end_lines.json`, with provenance per
  harness (version, date, command) in the file:
  - **Claude Code 2.1.312:** the init line and the first two `result` lines of
    one resumed session from this repo's worker log `w-0008` (2026-10-28).
  - **Codex 0.165.0:** `codex exec --json --skip-git-repo-check "reply ok"`
    from an empty temp dir (2026-11-02).
  - **Cursor `agent` 2026.10.22-27dcf5f:** `agent -p --output-format stream-json
    --force "reply ok"` from an empty temp dir (2026-11-02, model Grok 4.6
    High). Its `result` line.

  Sanitizing replaced session, thread, request, run and message ids, the result
  text and an account flag with `<placeholders>`. The Claude init line keeps
  only `type`, `subtype`, `model`, `claude_code_version` and `permissionMode`
  (it carried cwd, memory and socket paths, plugins). Token and cost figures
  are as recorded.

  The records changed the mapping in one place. Claude reports reasoning as
  `usage.output_tokens_details.thinking_tokens`, which now fills
  `reasoning_tokens`; it was `null`.

  They also confirmed the cost design. Across the resume, `total_cost_usd` is
  the session's running total (1.0474079 → 1.2101441), and the delta matches the
  line's own `model_usage_since_last_result` cost. `usage` tokens and
  `num_turns` are per run, so they are not differenced.

  Two inputs in the tests are still constructed, and are marked as such in the
  tests: Codex `turn.failed`, and a Cursor `result` line with `usage` removed.

## Touch zones (final)

All nine listed zones were used. One path outside them was added in round 1
because the coordinator asked for recorded fixtures (R3):
`tests/fixtures/worker_usage/turn_end_lines.json`. The test files are at or near
the 400-line cap, so the recorded lines could not be inlined.

Not edited:
- `docs/orchestration-models.md`. The planning sheet's Approach names its
  "prices section", but the file has no prices section (only a "Cost" ranking
  bullet), it is outside the touch zones, and no acceptance item needs it.
- `CHANGELOG.md`. It is outside the touch zones.

## Notes for reviewers

- Cursor's `inputTokens` is read as excluding cache reads (Anthropic-style
  buckets: input + `cacheReadTokens` + `cacheWriteTokens`). The one recorded
  line (9323 input, 4864 cache read) cannot prove inclusive or exclusive, so
  this reading is still an assumption.
- Codex's recorded line also carries `cache_write_input_tokens` (0). It is not
  read: Codex's `input_tokens` is already the total input.
- The Claude cost delta assumes one session per worker. If a human used the
  session between turns (handoff), their spend lands in the next turn's delta.
- Totals add up what was reported. When some turns are `null` for a figure, the
  sum is a lower bound. The docs say so.
- Summed `cost_usd` and the Claude delta are rounded to 6 decimals, which
  removes float noise such as `0.08 - 0.05`.

## Verification

Round 1, at commit `d256600`, foreground:
- `pytest tests/test_worker_adapters.py tests/test_worker_cli.py`: 33 passed.
- `ruff check specy_road tests`: clean. `specy-road file-limits`: OK.

Round 0 (`b4ac17a`) also ran the other worker tests (80 passed), the other tests
that use the worker modules (272 passed) and the CLI and doc tests (97 passed).
The full `pytest` suite has not been run to completion: in round 0 it exceeded
the harness's 20-minute background limit and was stopped. The reviewer's run
failed `test_terminate_a_live_worker` with "ps unavailable". It passes here,
and this change does not touch terminate.

## Added

- `worker_adapter_parsers.USAGE_FIELDS`: the eight field names in one place, used by the wrapper (all-null fill) and the schema test.
- `worker_adapter_parsers._num`: guard that turns a non-number, bool or negative value into `null`, so a model-controlled line cannot fail schema validation and drop the event.
- `worker_adapter_parsers.usage_fields`: the per-harness → shared-shape mapping (A2), including the branch that adds Anthropic-style cache buckets (reads, writes, either alone) back into `input_tokens` (R2) and the `output_tokens_details.thinking_tokens` fallback for `reasoning_tokens` (from the R3 records).
- `worker_adapter_parsers.usage_text`: one-line rendering shared by the event summary and `worker usage`.
- `worker_adapters.Parsed.usage`: carries the figures from `parse` to the wrapper without changing existing `detail` shapes.
- `worker_runner._append_usage`: writes the `usage` event, with the cumulative → delta conversion (A2) and `harness_version` taken from `started`.
- Branch in `_append_usage`: a total lower than the previous one counts whole. Without it a new session under a custom command would give a negative cost.
- Branch in `_finish`: an all-`null` `usage` event when the turn reported none, for one event per turn end (A2).
- Call in `run`'s launch-`OSError` path: the same all-`null` `usage` event before the exit-127 error (R1).
- `_consume` return value / `usage_logged` in `run`: tells `_finish` whether the turn already logged usage.
- `worker_cli_render._sum_usage`, `usage`, `usage_lines`: aggregation and text (A3).
- `worker_cli._records_for`, `cmd_usage`, `usage` subparser: the command (A3). `_records_for` replaces the inline lookup in `cmd_timeline`.
- Schema `if`/`then` + `$defs/usage`: A1.
- Mocks: none. Tests use the existing fake-harness scripts.
- Fixture `tests/fixtures/worker_usage/turn_end_lines.json`: recorded, sanitized turn-end lines per harness with provenance (R3).
- Test `test_each_adapter_reports_turn_usage_in_one_shape` (test_worker_adapters.py): A2 per harness from the recorded lines (Claude, Codex, Cursor camel case), plus a constructed Cursor line without usage → `null`, a cache-write-only bucket (R2), bad types → `null`, and generic → no usage.
- Test `test_usage_events_per_turn_and_the_usage_command` (test_worker_cli.py): A2 through the wrapper on the recorded lines (Claude delta 1.0474079 → 0.162736 across the recorded resume, version 2.1.312 from init, recorded Codex turn, all-`null` event on a constructed `turn.failed`) and A3 (`--json`, exact text lines, worker-id target, unknown node exits 1).
- Test `test_usage_event_schema_needs_every_field_nullable_never_missing` (test_worker_cli.py): A1, where nulls and zeros pass and a missing field, wrong type or missing detail fail.
- Helper `_turn` (test_worker_cli.py): runs one fake-harness turn through `worker_runner.run`.
- Extended `test_run_reports_a_missing_binary_as_failed`: asserts the all-`null` usage event before the exit-127 error (R1).
- Updated expectations (not loosened): three event-sequence assertions in test_worker_adapters.py now include the `usage` event that A2 adds at the turn end.
