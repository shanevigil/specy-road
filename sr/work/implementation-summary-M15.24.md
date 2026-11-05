# Implementation summary — M15.24

## Scope

Leaf `M15.24` (`ready-flags-failure-tails-and-takes-argv`): `specy-road ready` flags exit-zero runs whose recorded tail shows a failed command, and adds `--run-argv` to run verifiers without a shell.

## Touch zones (confirmed)

- `specy_road/ready_run_checks.py`, `specy_road/review_gate_ready.py`, `specy_road/bundled_scripts/review_packet.py`, `tests/` (plus `specy_road/schemas/handoff.schema.json` for optional verify `warning`).

## Behaviour (summary)

- Exit-0 tails matching `FAILURE_MARKERS` get a `warning` on the verify row and in the packet; READY still writes.
- `--run-argv`: non-empty JSON string array; first element non-empty; no NUL in any element; later elements may otherwise be empty.
- Every `--run` / `--run-argv` validated in `prepare_live_runs` before any live verifier; blank or NUL-containing `--run` refuses the whole command.
- `_subprocess_output` is the sole launch wrapper: any exception while starting a verifier becomes exit 126 or 127 with error text in `tail`, then the usual failing-verifier refusal (no READY).

## Fix round (REVIEW-gpt-6.1-sol-low, embedded NUL)

- **`parse_run_argv`:** Refuses `\\0` in any element with `argv[i]` in the message.
- **`prepare_live_runs`:** Refuses NUL in raw `--run` strings before execution.
- **`_subprocess_output`:** Catches `Exception` (not only `OSError`) so launch cannot crash `cmd_ready`.

## Verification

- `pytest -n 4 -q $(rg -l 'ready_run_checks|review_gate_ready|import review_packet|from specy_road.bundled_scripts.review_packet' tests) tests/test_schema_revision.py`
- `ruff check specy_road tests scripts`
- `specy-road file-limits`

## Probes

- **NUL in `--run-argv` JSON (program or later arg):** `parse_run_argv` raises before `prepare_live_runs` returns; CLI test with prior `--run touch` confirms marker file and READY absent.
- **NUL in `--run` shell command:** `prepare_live_runs` refuses with embedded NUL message; no `_live_run_rows` call.
- **Launch `ValueError` (embedded null if validation bypassed):** `_subprocess_output` maps to exit 126 and tail text; monkeypatched `subprocess.run` covers `--run` and `--run-argv` paths.
- **`FileNotFoundError` / other `OSError`:** Still exit 127/126 via `_launch_failure_exit`; existing launch parametrized tests pass.
- **Valid argv after validation:** Empty later strings, whitespace, unicode unchanged; accept tests pass.
- **`review_packet` / marker warnings:** Unchanged; selected pytest still passes.

## Added

- NUL scan in `parse_run_argv` and `prepare_live_runs` for `--run`.
- `_launch_failure_exit` + total `except Exception` in `_subprocess_output`.
- `test_parse_run_argv_refuses_embedded_nul`, `test_ready_run_argv_embedded_nul_refuses_before_any_live_run`, `test_subprocess_launch_exception_becomes_failing_row`.
