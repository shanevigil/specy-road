# Implementation summary: M11.72 — reviewer-failure-visible

## What changed

Reviewer runs through `review delegate` or `prompt --role reviewer --channel cli` now compare the review record after the run to the commit under review. When no valid `REVIEW-<model>.md` exists, the run closes as `incomplete`, appends a `reviewer-failure` event (with the harness error line from output) to `RUN-<model>.json`, and `handoff status` shows that failure on the policy line next to `not met` instead of only generic approval counts.

## Touch zones (confirmed)

- `specy_road/review_delegate.py` — delegate close path uses shared failure recording
- `specy_road/reviewer_run_failure.py` — **new** (file-limits split from delegate)
- `specy_road/bundled_scripts/review_cli.py` — `gate_policy_summary` on handoff policy line
- `specy_road/bundled_scripts/role_prompt.py` — reviewer `--channel cli` RUN tracking and transcript capture (required by A1; not listed on the node originally)
- `tests/test_review_delegate.py`, `tests/test_review_files.py`

`specy_road/review_gate.py` was not edited; policy wording is composed in `reviewer_run_failure.gate_policy_summary`.

## Verification

- `specy-road file-limits`
- `pytest tests/test_review_delegate.py`

## Added

- `specy_road/reviewer_run_failure.py` — module for valid-record check, failure events, prompt-cli RUN open/close, and gate policy suffix
- `harness_error_line` — picks capacity/usage-limit or tail output for the event error field
- `record_reviewer_failure_event` — appends `{type: reviewer-failure, error}` to RUN `events`
- `reviewer_failure_gate_note` / `gate_policy_summary` — surfaces failure beside `policy: … not met`
- `open_reviewer_cli_run` / `close_reviewer_cli_run` — same RUN contract for `prompt --channel cli`
- `close_run` — shared delegate/cli completion and failure recording
- `test_handoff_policy_line_names_a_usage_limit_reviewer_failure` — delegate usage limit on policy line and event
- `test_successful_delegate_run_has_no_reviewer_failure_event` — complete delegate run has no failure events
- `test_prompt_cli_channel_records_usage_limit_and_shows_it_on_the_gate_line` — prompt cli path and handoff line
- none (mocks)
