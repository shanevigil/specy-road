# Implementation summary — M15.24

## Scope

Leaf `M15.24` (`ready-flags-failure-tails-and-takes-argv`): `specy-road ready` flags exit-zero runs whose recorded tail shows a failed command, and adds `--run-argv` to run verifiers without a shell.

## Touch zones (confirmed)

- `specy_road/ready_run_checks.py` — new module (call sites: `review_gate_ready.py`; M15.23 will extend here).
- `specy_road/review_gate_ready.py` — imports run helpers; `--run-argv` in `cmd_ready` / `add_ready_parser`.
- `specy_road/bundled_scripts/review_packet.py` — `_ready_verify` prints `**Warning:**` when a verify row has `warning`.
- `tests/` — extended `tests/test_ready_command.py`.

Also changed (required for READY schema validation, not listed on the node): `specy_road/schemas/handoff.schema.json` — optional `warning` on verify items.

## Behaviour

- **A1:** `run_check` / `run_argv` live in `ready_run_checks.py`. On exit 0, `tail_warning` scans the recorded tail for `FAILURE_MARKERS`; the first matching line is stored as `warning` on the verify row and printed as `warning: …` on stderr. READY is still written.
- **A2:** `_ready_verify` adds one bold warning line under the verifier heading. Tests cover a loop whose failing step prints `cannot open` and whose last step succeeds (exit 0), plus a clean run without `warning`.
- **A3:** `--run-argv` parses JSON (non-empty array of strings) before any run; execution uses `subprocess` without `shell=True`; `cmd` is `shlex.join(argv)`. Invalid JSON or shape is refused without running verifiers.

## Fix round (REVIEW-grok-4.7-low)

- **`--run-argv` help:** Reworded so invalid JSON or anything other than a non-empty JSON array of strings is refused; help lists refused and accepted examples; tests pin each example to `parse_run_argv` / `ready`.
- **`_finish`:** Uses `stdout` directly; callers always pass `r.stdout or ""`, so no None path remains.

## Verification

- `pytest tests/test_ready_command.py tests/test_review_packet.py tests/test_schema_revision.py -n 4 -q`
- `ruff check specy_road/ready_run_checks.py specy_road/review_gate_ready.py tests/test_ready_command.py`
- `specy-road file-limits`

## Probes

- **`--run-argv` help vs `parse_run_argv`:** Help examples for refused (`not-json`, `[]`, `{}`, `[1]`, `[""]`) and accepted (`["echo", "ok"]`) match raises/return; `test_run_argv_help_examples_match_parse_run_argv` guards drift.
- **`parse_run_argv` docstring vs behaviour:** Doc says non-empty JSON array of strings; empty list, non-list, non-string elements raise `ValueError` with the same message shape as before.
- **`run_check` / `run_argv` module docstrings vs behaviour:** Shell and no-shell entry points unchanged; tails and warnings still flow through `_finish`.
- **`_finish(stdout)` call sites:** Only `run_check` and `run_argv`; both pass `r.stdout or ""` so `_tail` never sees `None`.
- **`--run` / `--verify` / `--red-green` help (this leaf touched `--run-argv` only):** Existing strings still describe non-zero refusal and red-green placement; behaviour unchanged in fix round.
- **`cmd_ready` docstring vs live runs:** Still runs cheap refusals before `--run` / `--run-argv`; `_live_run_rows` preserves prior loop semantics (stderr `running:` / `warning:` ordering).
- **`review_packet._ready_verify` warning line:** Unchanged in fix round; packet tests still pass.

## Added

- `specy_road/ready_run_checks.py` — module housing run execution, tail capture, failure markers, and argv parsing.
- `FAILURE_MARKERS` — the four case-sensitive substrings acceptance names for tail scanning.
- `tail_warning(tail)` — returns the first tail line containing any marker.
- `_tail` / `_finish` — shared tail truncation and verify-row assembly including optional `warning`.
- `run_argv(argv)` — non-shell run with `shlex.join` cmd label.
- `parse_run_argv(spec)` — JSON validation before runs.
- `_live_run_rows` — runs `--run` and `--run-argv` verifiers; shared refusal message shape for ruff complexity.
- `cmd_ready` branches — stderr warning print; `--run-argv` loop via `_live_run_rows`; refusal when `not all(runs) and not argv_runs` (preserves verify-only hand-offs).
- `--run-argv` argparse entry — repeatable JSON argv runs with corrected help and documented examples.
- `_ready_verify` warning line — bold packet output for verify `warning`.
- `handoff.schema.json` `warning` property — so READY rows with warnings pass load validation.
- `test_ready_run_warns_when_exit_zero_but_tail_shows_cannot_open` — loop reproduction; asserts READY, stderr, and packet.
- `test_ready_run_clean_tail_has_no_warning` — clean run has no `warning` key or packet bold line.
- `test_ready_run_argv_without_shell_and_refuses_bad_json` — `$f` and spaces unexpanded; bad JSON / empty array refused without mutating prior READY.
- `RUN_ARGV_HELP_REFUSED` / `RUN_ARGV_HELP_ACCEPTED` — constants kept in sync with `--run-argv` help examples.
- `test_run_argv_help_examples_match_parse_run_argv` — each help-listed refused/accepted shape hits `parse_run_argv`.
- `test_ready_run_argv_help_accepted_example_runs` — help accepted example runs through `ready` and records output tail.
