# Implementation summary — M15.13

Worker loop friction: sync `--until`, collapsed tool-use output, rework after a completed worker, READY-only resume, quieter pickup hint.

## Touch zones (confirmed)

- `specy_road/bundled_scripts/worker_cli.py` — delegate/resume wiring; sync moved out
- `specy_road/bundled_scripts/worker_cli_sync.py` — **new** `cmd_sync`, `--until` / `--verbose`, wait helpers
- `specy_road/bundled_scripts/worker_cli_render.py` — collapsed tool-use lines; READY-missing completion hint
- `specy_road/worker_state.py` — `wait_for_event(..., event_types=…)` delegates typed wait
- `specy_road/bundled_scripts/role_prompt_rework.py` — `rework_check` allows `completed`
- `specy_road/on_complete_pickup.py` — grind-session hint once per checkout
- `specy_road/worker_ops_message.py` — `resume(..., ready_only=…)`
- `specy_road/worker_runner_ready.py` — `READY_ONLY_PROMPT`
- `docs/orchestration-workers.md` — links and table rows
- `docs/orchestration-worker-sync.md` — **new** sync wait/until/verbose doc
- `tests/` — `test_worker_sync_m15_13.py`; pickup and worker_state test updates

No zone additions or removals beyond the new sync module and doc.

## Acceptance

| Id | What |
|----|------|
| A1 | `worker sync --wait --until completion\|error\|intervention`; typed wait; `worker_cli.py` ≤400 lines |
| A2 | Collapsed `#N-#M output: K tool uses`; `--verbose` opts out |
| A3 | `delegate --rework` with `completed` worker proceeds; note names it |
| A4 | Completion missing READY suggests `worker resume W --ready-only`; fixed prompt |
| A5 | Pickup hint once via `.specyrd/cache/pickup-orchestration-hint` |

## Verification

- `specy-road file-limits`
- `python -m pytest -q -n 4 tests/test_worker_sync_m15_13.py tests/test_pickup_orchestration_hint.py tests/test_worker_cli.py tests/test_worker_state.py tests/test_rework_findings_in_prompt.py tests/test_rework_rca.py`
- `ruff check specy_road tests scripts`

## Fix round (grok-4.7-low)

- **`cmd_sync` exit code:** `--wait` success is only when the wait condition is met (`wait_for_sync` returns true). Exit 2 when `timed_out`, even if the final delta lists other unacknowledged events (unmatched `--until` types).
- **READY-only test:** `worker resume W --ready-only` via CLI; assert `work/prompt-W-ready-only-*.md` content matches `READY_ONLY_PROMPT` (no patch of `_send`).

## Probes

- **`cmd_sync` return when `timed_out` and non-empty delta:** only path is `return 2 if timed_out else rc`; reviewed `worker_cli_sync.cmd_sync` — fixed class, no other branches.
- **`--wait` without `--until` on timeout:** `timed_out` true, empty delta → exit 2; covered by existing `test_sync_wait_ends_on_an_event_or_times_out_with_exit_2`.
- **`wait_for_sync` / `wait_for_typed_event`:** still return bool “condition met”; exit code derived only in `cmd_sync` — checked both helpers, unchanged contract.
- **Other CLI commands with `--timeout`:** only `worker sync` parser defines `--timeout` with `--wait`; no parallel exit-code pattern in touch zones.
- **READY-only prompt assertion surface:** `worker_ops_message._send` writes `work/prompt-{id}-{kind}-{n}.md` before spawn; CLI test reads that path — checked `resume` and `run_worker_cli` path, no `_`-prefixed test imports or patches.
- **Parametrized `--until` values:** `completion`, `error`, `intervention`, comma lists — condition met, timeout empty, timeout with output-only delta.

## Added

- `worker_cli_sync.py` module (`parse_sync_until`, `wait_for_typed_event`, `wait_for_sync`, `cmd_sync`, `add_sync_parser`): A1/A2 CLI surface and wait loop without bloating `worker_cli.py`
- `wait_for_event` `event_types` branch delegating to `wait_for_typed_event`: A1 typed filter entry point on `worker_state`
- `_tool_use_only`, `sync_event_lines`, READY-missing line in `_sync_event_lines`: A2 collapse and A4 sync hint
- `rework_check` completed-worker branch and stderr note line: A3
- `_orchestration_hint_marker` and marker write in `print_orchestration_hint`: A5
- `READY_ONLY_PROMPT` and `resume(..., ready_only=…)`: A4
- `docs/orchestration-worker-sync.md`: operator doc for sync wait/until/verbose
- `tests/worker_cli_helpers.py` (`run_worker_cli`, `wait_for_worker`): public CLI test helpers (no `_`-prefixed imports in M15.13 tests)
- `tests/test_worker_sync_m15_13.py`: A1–A4 behaviour tests
- `test_the_footer_carries_the_hint_once_per_checkout`: A5
- `test_worker_state` Ctrl-C patch target `worker_cli_sync.wait_for_sync`: sync moved out of `worker_cli.py`
