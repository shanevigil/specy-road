# Implementation summary: M10.9 — emit a stalled event when a worker goes silent

Branch `feature/rm-emit-a-stalled-event`; implementation commit `3b649f6`.

## What changed, per acceptance item

- **A1** — `WorkerRecord.last_output_at` (`specy_road/worker_state.py`). In
  `worker_runner.run()` the wrapper writes it through `_output_seen()` on a
  stdout line only when its last write is at least `OUTPUT_MARK_SECONDS` (5)
  old, read from a monotonic clock (`_clock`). Each write is a `mutate` under
  the workers lock. The `seen` mutate at launch sets it to the launch time, so
  every turn starts a new silence (design point 1 from the stop report).
- **A2** — `worker_ops.sweep_stalled(repo_root, *, now=None)`. For each active
  record in `running` whose `last_output_at` is at least
  `policy.stall_after_seconds` old and not already flagged, it appends one
  `stalled` event (source/authority `system`; summary and detail carry the
  seconds silent, `last_output_at` and the last worker-sourced summary) and
  adds flag `stalled`. A record that has left `running`, or is under the
  threshold again, loses the flag. `worker_reconcile.sync` calls it right
  after `sweep_dead_wrappers` (so a dead wrapper is `failed`, not stalled), and
  `worker_cli.cmd_list` calls it before listing. Clearing: the wrapper's next
  `last_output_at` write drops the flag in the same mutate (design point 2).
  After a 600 s silence that write is always outside the 5 s window, so the
  first line clears the flag. A later silence raises it again.
- **A3** — `worker-record.schema.json` gains `last_output_at` and the
  `stalled` flag; `worker-event.schema.json` gains event type `stalled`.
  `orchestration_config.DEFAULT_POLICY["stall_after_seconds"] = 600`.
- **A4** — `docs/orchestration-workers.md`: `last_output_at` field row,
  `stalled` in the flags row and in the event list (388 lines, cap 400).
  `docs/orchestration.md`: `policy.stall_after_seconds` row in the policy
  table. Tests below use fake clocks (`_clock` readings, `now=`).

## Open: the policy key cannot be set yet (outside the touch zones)

`specy_road/templates/project/schemas/orchestration.schema.json` declares
`policy` with `additionalProperties: false`. A `roadmap/orchestration.yaml`
that sets `policy.stall_after_seconds` is therefore rejected
(`policy: Additional properties are not allowed ('stall_after_seconds' was
unexpected)`, checked with `parse_orchestration_text`). Until that schema
gains the key, only the default 600 applies, though the docs present the key
as settable. The fix is one property (`integer`, `minimum` 1, "Default 600")
in that file plus a test that an override takes effect. That file is not in
M10.9's touch zones, so READY is held.

## Render

`worker_cli_render._line` already prints every flag in `[...]` and `_row`
returns the record's fields (now including `last_output_at`), and sync prints
every event, `stalled` included. No change was needed in
`worker_cli_render.py`.

## Final touch zones used

`specy_road/worker_runner.py`, `specy_road/worker_state.py`,
`specy_road/worker_ops.py`, `specy_road/orchestration_config.py`,
`specy_road/schemas/worker-event.schema.json`,
`specy_road/schemas/worker-record.schema.json`,
`specy_road/worker_reconcile.py`, `specy_road/bundled_scripts/worker_cli.py`,
`docs/orchestration-workers.md`, `docs/orchestration.md`,
`tests/test_worker_faults.py`. Untouched from the list:
`specy_road/bundled_scripts/worker_cli_render.py` (above),
`tests/test_worker_state.py`. Needed and outside:
`specy_road/templates/project/schemas/orchestration.schema.json`.

M10.5 coordination: no edit to `worker_ops._cli_for`, the launch/resume
calls, or the child env / `Popen` in `worker_runner`. The runner changes are
in the `seen` mutate, the read loop and a new function below `run`.

## Verification

- `pytest tests/test_worker_faults.py tests/test_worker_state.py`: 14 passed
  (foreground). Only the touched test files were run, as instructed; the full
  suite is the coordinator's.
- Setting `OUTPUT_MARK_SECONDS` to 0 makes the throttle test fail (checked,
  then reverted).
- `ruff check` on every touched Python file: clean. An `if` inside `seen` had
  pushed `run` to C901 11, so both flag removals use a comprehension.
- `specy-road file-limits`: OK. `worker_ops.py` is 393 lines (cap 400);
  M10.5 also adds to that file, so the merge should watch the cap.

## Added

- `FLAG_STALLED` (`worker_state.py`): the flag name, shared by the runner and the sweep.
- `WorkerRecord.last_output_at` (`worker_state.py`): A1's field.
- `OUTPUT_MARK_SECONDS` and `_clock` (`worker_runner.py`): the 5 s write window, and a clock tests can replace.
- `_output_seen()` (`worker_runner.py`): throttled `last_output_at` write that also clears `stalled` (A1, A2 clear).
- Reset in the `seen` mutate (`worker_runner.py`): `last_output_at` = launch time and `stalled` dropped at each turn start, so a resumed worker is not judged on the last turn's silence.
- `_output_seen` call inside the existing per-line `try` (`worker_runner.py`): a failed write is logged like a bad line and does not kill the wrapper.
- `sweep_stalled()` (`worker_ops.py`): A2's mark, event and clear-on-leave-running; `now=` is the fake-clock seam.
- Guard in `sweep_stalled`: an unreadable pinned config still uses the default threshold.
- Call in `worker_reconcile.sync` after `sweep_dead_wrappers`, and in `worker_cli.cmd_list` before listing (A2's two commands).
- `stall_after_seconds: 600` in `DEFAULT_POLICY` (`orchestration_config.py`): A3.
- Schema: `last_output_at` and flag `stalled` in the record schema, type `stalled` in the event schema (A3).
- Test `test_last_output_at_is_written_at_most_every_five_seconds`: A1 throttle with a fake clock through `run()`.
- Test `test_a_new_turn_resets_last_output_at_and_the_stalled_mark`: the turn-start reset.
- Test `test_a_silent_running_worker_is_flagged_once_per_silence`: A2 threshold, one event per silence, clear on output, re-raise, clear on leaving `running`, with `now=`.
- Test `test_list_and_sync_flag_a_live_silent_worker`: A2 through `worker list` and `worker sync` on a live spawned wrapper.
- Test helpers `SILENT_THEN_LINES`, `_stamps` (a fake `worker_runner._now` that counts writes), `_turn`, `_stalled`: support for the tests above.
- Mocks: `monkeypatch` of `worker_runner._clock` and `worker_runner._now` only.
