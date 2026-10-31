# Implementation summary: M10.1 — Record phase timestamps in the event log and print a per-leaf timeline

Branch `feature/rm-record-phase-timestamps-in`, base `6e7b291` (WIP after the second touch-zone widening), implementation commits `1922d6e` (A1 to A4) and the follow-up that updates `tests/test_worker_adapters.py`.

## What changed, per acceptance criterion

- **A1** (`specy_road/worker_runner.py`, `specy_road/schemas/worker-event.schema.json`): `run()` appends `launched` (source `system`, detail `{argv0, harness, resumed}`) right after `Popen` succeeds and the harness pid is recorded, and `first_output` (source `system`, no detail) on the first stdout line, before `_consume`. Both carry the existing `at` and nothing else new. The schema enum gains the two names.
- **A2** (`specy_road/worker_reconcile.py`): `sync(..., ack=True)` now writes `{"seq": <highest acked>, "acked_at": <iso>}` per worker in `work/.workers/sync.yaml`. A new reader `sync_marks()` normalises both the new shape and the earlier bare-integer shape, so an existing file still reads. What `sync` returns is unchanged.
- **A3** (`specy_road/bundled_scripts/worker_cli.py` 346→363 lines, `worker_cli_render.py` 71→135 lines): `specy-road worker timeline W|NODE_ID [--json]`. The CLI module only resolves the target (a `w-` id, or the latest record for a node id, error `no worker for X` otherwise) and emits. The render module finds the latest turn (from the last broker/orchestrator `started` or `message`; a harness's worker-sourced `started` does not start a turn), takes the first `launched`, `first_output` and turn-end (`turn_completed`, `completion`, or `error` carrying `exit`) in it, and the sync ack only when its `seq` reaches the end event's. Phases print as whole seconds or `unknown`; `--json` gives `{"worker_id","node_id","phases":{name: seconds|null}}`.
- **A4** (`docs/orchestration-workers.md` 374→377 lines): event list names `launched` and `first_output` with their detail; `sync` row notes `seq`/`acked_at`; new `timeline` row.

## Touch zones

As widened in `39504ef` and `6e7b291` (`tests/test_worker_adapters.py` added); every changed path is inside them.

## Verification

- `specy-road file-limits` → `OK: file limits satisfied.`
- `pytest tests/test_worker_state.py tests/test_worker_cli.py tests/test_worker_faults.py tests/test_review_round6_ops.py` → 48 passed (first run had one failure in my own new test from an unread capsys buffer; fixed, re-run green).
- Review round 1 (gpt-6.1-sol TI1): the sync-lock test in `tests/test_review_round6_ops.py` compares the whole `sync.yaml` mapping exactly again, `{worker: {seq, acked_at}}`. It checks first that `acked_at` parses as ISO and falls between the lock release and the end of the check. After the fix, `pytest tests/test_worker_state.py tests/test_worker_cli.py tests/test_worker_faults.py tests/test_review_round6_ops.py tests/test_worker_adapters.py -q` → 56 passed; `specy-road file-limits` OK.
- `pytest tests/test_worker_adapters.py` → 8 passed, after `test_run_records_session_id_events_and_a_clean_exit` (line 129) was updated to expect `launched` and `first_output` after the delegation's `started`; its other assertions are unchanged. The only other sequence check in that file (`[-2:] == ["error", "error"]`, line 151) is a tail and still holds.

## Not done / needs the coordinator

- none.

## Added

### Helpers
- `worker_reconcile.sync_marks(repo_root)` — one reader for `sync.yaml` shared by `sync` and the timeline; accepts the legacy integer shape.
- `worker_cli_render.PHASES` — the four `(name, start, end)` tuples, so text and JSON render from one list.
- `worker_cli_render._parse_at` — ISO `at` to `datetime` (tolerates a `Z` suffix).
- `worker_cli_render._delegation` — is this event a coordinator `started`/`message` (turn start), not the harness's own `started` line.
- `worker_cli_render._latest_turn` — slice of the log from the latest delegation on.
- `worker_cli_render._boundaries` — the five timestamps (or `None`) for the latest turn, including the ack gate on `seq`.
- `worker_cli_render.timeline` — the JSON object; `timeline_lines` — its text lines.
- `worker_cli.cmd_timeline` — target resolution and emit only (argparse wiring in `build_parser`).

### Branches or guards
- `worker_runner.run`: `first` flag so `first_output` is appended once, on the first stdout line.
- `worker_reconcile.sync_marks`: dict vs integer value per worker (legacy file shape).
- `worker_cli_render._boundaries`: the ack counts only when `marks.seq >= end.seq` (an earlier turn's ack is not this turn's).
- `worker_cli.cmd_timeline`: `w-` prefix selects a worker id, else the node id's latest record; `WorkerError` when none.

### Mocks
- none (the existing `FAKE` harness script and `make_review_repo` fixture are reused).

### Tests
- `tests/test_worker_cli.py::test_launch_events_ack_time_and_timeline` — A1 event order and `launched` detail (`resumed` false then true), A2 file shape and unchanged `sync` output, A3 text by node id before ack, JSON by worker id after ack, resumed turn's `end_to_acked` unknown, unknown node refused.
- `tests/test_worker_cli.py::test_timeline_arithmetic_and_unknown_phases` — fixed log: exact seconds, text lines, ack short of the end, `error` with `exit` as turn end, missing `first_output`, adopted worker all unknown.
- `tests/test_worker_faults.py` (existing test extended) — a killed harness still logs `launched` < `first_output` < `error`.
- `tests/test_worker_state.py` (existing test extended) — the schema accepts `launched` with its detail and `first_output`; count adjusted.
- `tests/test_review_round6_ops.py` (existing sync-lock test extended) — exact equality on the new `{seq, acked_at}` shape, with `acked_at` parsed and bracketed by the lock release and the check; the mark still acknowledges; a legacy integer file reads via `sync_marks`.
- `tests/test_worker_adapters.py::test_run_records_session_id_events_and_a_clean_exit` (existing test, one line) — the expected event sequence gains `launched`, `first_output` between the broker's `started` and the harness's; nothing loosened.
