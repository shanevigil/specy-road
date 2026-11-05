# Implementation summary — M15.24

## Scope

Leaf `M15.24` (`ready-flags-failure-tails-and-takes-argv`): `specy-road ready` flags exit-zero runs whose recorded tail shows a failed command, and adds `--run-argv` to run verifiers without a shell.

## Touch zones (confirmed)

- `specy_road/ready_run_checks.py`, `specy_road/review_gate_ready.py`, `specy_road/bundled_scripts/review_packet.py`, `tests/` (plus `specy_road/schemas/handoff.schema.json` for optional verify `warning`).

## Behaviour (summary)

- Exit-0 tails matching `FAILURE_MARKERS` get a `warning` on the verify row and in the packet; READY still writes.
- `--run-argv`: non-empty JSON string array; first element non-empty; later elements may be empty.
- Every `--run` / `--run-argv` validated before live execution; blank `--run` refuses even with `--run-argv`.
- `subprocess` launch `OSError` (missing binary, non-executable file, directory as program) becomes exit 127 or 126 with error text in `tail`, then the usual failing-verifier refusal (no READY).

## Fix round (REVIEW-gpt-6.1-sol-low, launch + tests + docs)

- **`_subprocess_output`:** Single launch path for `run_check` and `run_argv`; catches `OSError` at the subprocess boundary.
- **Parser tests:** `RUN_ARGV_PARSE_REFUSED` owns refusal behaviour; help test only asserts examples appear in help text.
- **`run_check` / `run_argv` docstrings:** Restore `{cmd, exit, tail}` and note optional `warning` and launch-failure exits.

## Verification

- `pytest -n 4 -q $(rg -l 'ready_run_checks|review_gate_ready|import review_packet|from specy_road.bundled_scripts.review_packet' tests) tests/test_schema_revision.py`
- `ruff check specy_road tests scripts`
- `specy-road file-limits`

## Probes

- **`run_argv` missing executable:** `FileNotFoundError` → exit 127, tail text; `ready` CLI test asserts refusal and no READY.
- **`run_argv` not executable / directory / bad shebang:** Parametrized launch cases → 126 or 127 without uncaught exception; no `warning` on non-zero exit.
- **`run_check` missing command (shell):** Exit 127 via shell, not `OSError`; separate test documents `--run` parity without duplicating argv launch table.
- **`_live_run_rows` non-zero exit path:** Launch-failure rows use same refusal branch as failing commands; no READY write.
- **`parse_run_argv` refusal table:** Help examples ⊆ `RUN_ARGV_PARSE_REFUSED`; help test no longer calls `parse_run_argv` for refused specs.
- **`prepare_live_runs` / blank `--run`:** Unchanged this round; combination tests still pass.
- **`review_packet` / tail warnings:** Unchanged; selected pytest still passes.

## Added

- `_launch_exit_code`, `_subprocess_output` — shared subprocess boundary; 127 for `FileNotFoundError`, else 126.
- `RUN_ARGV_PARSE_REFUSED` — single refusal case list for parametrized parse tests.
- `test_run_argv_launch_os_errors`, `test_run_check_missing_command_exits_127_without_oserror`, `test_ready_run_argv_missing_executable_refuses_without_writing_ready`.
