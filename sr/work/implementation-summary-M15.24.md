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
- **A3:** `--run-argv` parses JSON before any run: a non-empty array of strings whose **first** element is non-empty; later elements may be empty or whitespace. Every `--run` and `--run-argv` is validated before any live verifier executes; a blank or whitespace-only `--run` refuses the whole command even when `--run-argv` is also set.

## Fix round (REVIEW-grok-4.7-low, first)

- **`--run-argv` help:** Reworded; help examples pinned in tests.
- **`_finish`:** Uses `stdout` directly.

## Fix round (REVIEW-gpt-6.1-sol-low)

- **`parse_run_argv`:** Only the first argv element must be non-empty; later elements may be `""` or whitespace.

## Fix round (REVIEW-grok-4.7-low, blank `--run`)

- **`prepare_live_runs`:** Validates every `--run` (non-blank after strip) and every `--run-argv` before `_live_run_rows` or git-heavy checks that precede execution; removed `not all(runs) and not argv_runs` gate and the silent empty `--run` skip in `_live_run_rows`.

## Verification

- `pytest -n 4 -q tests/test_ready_command.py tests/test_review_packet.py tests/test_schema_revision.py tests/test_review_evidence.py`
- `ruff check specy_road/ready_run_checks.py specy_road/review_gate_ready.py tests/test_ready_command.py`
- `specy-road file-limits`

## Probes

- **Blank or whitespace-only `--run` with `--run-argv` present:** `prepare_live_runs` refuses before execution; parametrized test `blank_run_with_valid_argv` asserts no READY.
- **Each `--run` / `--run-argv` in isolation:** `prepare_live_runs` loops all raw `--run` values then all `--run-argv` specs; invalid argv refuses with `parse_run_argv` message before `_live_run_rows`.
- **`_live_run_rows` empty-cmd skip:** Removed; runs list only contains validated non-empty commands.
- **Verify-only hand-offs (no `--run` / `--run-argv`):** `raw_runs` and specs empty; `prepare_live_runs` returns empty lists, no error; existing verify-only tests still pass.
- **`parse_run_argv` later empty string (Sol-low):** Unchanged; `test_ready_run_argv_passes_empty_later_argument` still passes.
- **`cmd_ready` try/except:** Still catches `parse_check` and `resolve_target`; live-run validation moved out of that block so argv errors name the spec without conflating with verify parse errors.
- **Side-effect ordering:** `valid_run_invalid_argv_before_execute` uses `touch` plus invalid `[]` argv; file not created and READY absent.

## Added

- `specy_road/ready_run_checks.py` — run execution, tail capture, failure markers, argv parsing, and `prepare_live_runs`.
- `FAILURE_MARKERS`, `tail_warning`, `_tail`, `_finish`, `run_check`, `run_argv`, `parse_run_argv`, `prepare_live_runs`.
- `_live_run_rows` — executes validated run specs only.
- `--run-argv` argparse entry and `_ready_verify` warning line.
- `handoff.schema.json` `warning` property.
- Ready/tail/argv tests in `tests/test_ready_command.py`, including `test_ready_validates_every_run_and_run_argv_before_executing` (combination matrix).
