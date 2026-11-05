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

## Verification

- `pytest tests/test_ready_command.py -n 4 -q`
- `specy-road file-limits`

## Added

- `specy_road/ready_run_checks.py` — module housing run execution, tail capture, failure markers, and argv parsing.
- `FAILURE_MARKERS` — the four case-sensitive substrings acceptance names for tail scanning.
- `tail_warning(tail)` — returns the first tail line containing any marker.
- `_tail` / `_finish` — shared tail truncation and verify-row assembly including optional `warning`.
- `run_argv(argv)` — non-shell run with `shlex.join` cmd label.
- `parse_run_argv(spec)` — JSON validation before runs.
- `cmd_ready` branches — stderr warning print; `--run-argv` loop; refusal when `not all(runs) and not argv_runs` (preserves verify-only hand-offs).
- `--run-argv` argparse entry — repeatable JSON argv runs.
- `_ready_verify` warning line — bold packet output for verify `warning`.
- `handoff.schema.json` `warning` property — so READY rows with warnings pass load validation.
- `test_ready_run_warns_when_exit_zero_but_tail_shows_cannot_open` — loop reproduction; asserts READY, stderr, and packet.
- `test_ready_run_clean_tail_has_no_warning` — clean run has no `warning` key or packet bold line.
- `test_ready_run_argv_without_shell_and_refuses_bad_json` — `$f` and spaces unexpanded; bad JSON / empty array refused without mutating prior READY.
