# Implementation summary: M21.24 (claude-reviewer-schema-and-error)

## What changed

- **A1** `specy_road/worker_adapter_claude.py` `ClaudeCode.reviewer_launch`: the schema file is loaded and its
  top-level `$schema` key dropped before `json.dumps`; every other key and value (and order) is unchanged.
  `write_schema` is untouched, so `review-output.schema.json` keeps `$schema` for Codex and agy. `review delegate`
  and `prompt --role reviewer --channel cli --run` both build the argv here. Executor `launch`/`resume` never
  passed `--json-schema` and still do not.
- **A2** `specy_road/review_delegate.py` `_attempts`: when a turn failed and there is neither a capacity error nor
  a parsed error, `said` is the last non-blank (stripped) line of that turn's log span (`attempt_text`, the same
  span `run_text` reads), cut to 200 characters, or `no error text` when the span has none. `attempts[].error` and
  the `harness exited <code>: ` reason both use that one value. `delegate_turn`'s 20-line `tail` was not used:
  it keeps blank lines, so an error followed by >20 blank lines would be lost. Parsed-error and capacity paths
  are unchanged. Behaviour change: on a silent failure `attempts[].error` is now `"no error text"` (was `null`),
  as A2/A3 require the two fields to match.
- **A3** `tests/test_review_delegate_claude_schema.py` (new, so M21.21's tests/test_review_delegate.py is untouched).
- **A4** `docs/orchestration-reviewer-output.md` Claude Code row; `CHANGELOG.md` [Unreleased] Fixed entry.

Touch zones confirmed as listed; no change needed outside them.

## Verification

- New tests fail on the base code (5 of 6; the executor-argv test already held) and pass with the fix.
- `pytest -n 4` full suite: 5461 passed. `specy-road file-limits`: OK.

## Added

- `reviewer_launch`: `body` dict and `$schema` filter in the `--json-schema` value — Claude Code 2.1.318 rejects the draft 2020-12 `$schema` reference (A1).
- `_attempts`: `if failed and not said` branch reading the turn's log span's last non-blank line, cut to 200, else `no error text` — the reason and `attempts[].error` name the harness's own error (A2).
- Test helper `_repo` and fake `claude` script on PATH (`FAKE_CLAUDE`) — exercises the real `reviewer_launch` argv and a failing harness writing to stderr (A3).
- Test `test_the_inline_schema_is_the_file_less_its_dollar_schema` — argv `--json-schema` is the on-disk schema less `$schema`; the file keeps it (A1, A3).
- Test `test_a_failed_turn_names_the_harness_error_in_reason_and_attempt` (rc4 error, error then 25 blank lines, 250-char line, silent) — CLI reason and `attempts[].error` match the same expected text (A2, A3).
- Test `test_the_executor_launch_passes_no_json_schema` — executor launch/resume argv carry no `--json-schema` (A1, A3).
- Mocks: none beyond the fake `claude` binary.
