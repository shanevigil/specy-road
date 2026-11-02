# Implementation summary: M10.9 — emit a stalled event when a worker goes silent

Branch `feature/rm-emit-a-stalled-event`; implementation commits `3b649f6` (worker, sweep, docs, tests),
`abb7748` (orchestration schema key and its test), `f203c8b` (review round 1 fixes) and
`f8722e9` (review round 3 fixes), both rounds from `REVIEW-gpt-6.1-sol.md`.

## What changed, per acceptance item

- **A1** — `WorkerRecord.last_output_at` (`specy_road/worker_state.py`). In
  `worker_runner.run()` the wrapper writes it through `_output_seen()` on a
  stdout line only when its last write is at least `OUTPUT_MARK_SECONDS` (5)
  old, read from the monotonic clock `run(..., clock=time.monotonic)`. Each
  write is a `mutate` under the workers lock. The `seen` mutate at launch sets it to the launch time, so
  every turn starts a new silence (design point 1 from the stop report).
- **A2** — `worker_ops.sweep_stalled(repo_root, *, now=None)`. For each
  record in `running` whose `last_output_at` is at least
  `policy.stall_after_seconds` old and not already flagged, it appends one
  `stalled` event (source/authority `system`; summary and detail carry the
  seconds silent, `last_output_at` and the last worker-sourced summary) and
  adds flag `stalled`. It reads every record, so any record that has left
  `running` (idle, completed, failed, terminated, and the rest) loses the
  flag, as does one under the threshold again. `worker_reconcile.sync` calls it right
  after `sweep_dead_wrappers` (so a dead wrapper is `failed`, not stalled), and
  `worker_cli.cmd_list` calls it before listing. Clearing: the wrapper's
  `last_output_at` write drops the flag in the same mutate (design point 2).
  A line inside the 5 s window reads the record (no lock), and if it is
  flagged, the line writes the time and clears the flag right away. This is
  the R1 fix: with a threshold under the window, a sweep can flag a worker
  between two writes. Writing the time as well means the next sweep measures
  the new silence from this line. Routine writes stay at most one per 5 s;
  the only extra write is the one per stall that clears it. A later silence
  raises the flag again.
- **A3** — `worker-record.schema.json` gains `last_output_at` and the
  `stalled` flag; `worker-event.schema.json` gains event type `stalled`.
  `orchestration_config.DEFAULT_POLICY["stall_after_seconds"] = 600`.
- **A4** — `docs/orchestration-workers.md`: `last_output_at` field row,
  `stalled` in the flags row and in the event list (388 lines, cap 400).
  `docs/orchestration.md`: `policy.stall_after_seconds` row in the policy
  table. Tests below use fake clocks at public boundaries (`run(clock=...)`,
  `sweep_stalled(now=...)`) and assert persisted record and event state.

## Policy key in the orchestration schema

`specy_road/templates/project/schemas/orchestration.schema.json` declares
`policy` with `additionalProperties: false`. Before `abb7748` it rejected a
`roadmap/orchestration.yaml` that set `stall_after_seconds`, so only the
default applied. The touch zones were widened to take that file, and it now
declares `policy.stall_after_seconds` (integer, minimum 1, default 600). The
toolkit roadmap's own copy, `sr/schemas/orchestration.schema.json`, is
outside the zones and was left alone; it already differed from the template.

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
`specy_road/templates/project/schemas/orchestration.schema.json`,
`docs/orchestration-workers.md`, `docs/orchestration.md`,
`tests/test_worker_faults.py`. Untouched from the list:
`specy_road/bundled_scripts/worker_cli_render.py` (above),
`tests/test_worker_state.py`.

M10.5 coordination: no edit to `worker_ops._cli_for`, the launch/resume
calls, or the child env / `Popen` in `worker_runner`. The runner changes are
`run`'s signature (a new keyword, `clock`, last), the `seen` mutate, the read
loop and a new function below `run`.

## Review round 1 (gpt-6.1-sol, block)

- **R1** fixed as described under A2. `test_output_clears_a_stall_shorter_than_the_write_window`
  reproduces the reviewer's case through `run()` with real stdout and
  `stall_after_seconds: 1`. Against the old throttle-only clear it fails with
  `newly_flagged == [True, False]` (checked, then restored).
- **R2** fixed: the tests no longer patch `_now` or `_clock`, no longer call
  `_output_seen`, and no longer count timestamp calls. The throttle test feeds
  clock readings through `run(clock=...)` to a harness whose two lines are
  about 2.2 s apart, then checks the persisted `last_output_at` against the
  turn's `launched` event. The module-level `_clock` is gone.
- The reviewer's run failed in `test_list_and_sync_flag_a_live_silent_worker`'s
  cleanup (`terminate` could not verify the wrapper pid because `ps` was
  unavailable in their sandbox). They recorded this as an environment limit,
  not a regression, and the test passes here.

## Review round 3 (gpt-6.1-sol, block)

- **R1** fixed: `sweep_stalled` read only active records, so a worker that
  was flagged and then became `failed` or `terminated` kept the flag forever.
  It now reads every record. `test_a_silent_running_worker_is_flagged_once_per_silence`
  re-flags the worker and moves it to `idle`, `failed` and `terminated` in
  turn, and checks that each sweep clears the flag. With the old
  `active_only=True` it fails at `failed` (checked, then restored).
- **R2** fixed: `test_a_new_turn_resets_last_output_at_and_the_stalled_mark`
  no longer compares against the `launched` event, which is written after the
  reset and can land in the next wall-clock second. It now bounds the
  persisted `last_output_at` between a time taken before `run()` (rounded down
  to whole seconds, like the stamps) and one taken after it. The flag-clearing
  assertion is unchanged.

## Merge of origin/WIP/improvements-0-3-1 (`1c6f7a8`)

- One conflict, in `specy_road/templates/project/schemas/orchestration.schema.json`.
  M9.6 added `policy.integrity_gate` where this leaf added
  `policy.stall_after_seconds`. Both are kept: `stall_after_seconds`, then
  `integrity_gate`, each unchanged.
- Everything else merged automatically, including M10.5's changes to
  `worker_ops.py` and `worker_runner.py` and the `docs/brainstorming.md` cap
  fix (`9b82c16`). This leaf's code came through intact: `run(clock=...)`,
  the stall clear inside the window, and `sweep_stalled` reading every record.
- After the merge `worker_ops.py` is exactly 400 lines. `specy-road
  file-limits` still passes, but nothing more fits without a split.
- After the merge: `pytest tests/test_worker_faults.py tests/test_worker_state.py
  tests/test_orchestration_config.py tests/test_package_data_schemas.py
  tests/test_refresh_schemas.py` 48 passed; `specy-road file-limits` OK;
  `ruff check` on `worker_ops.py`, `worker_runner.py` and the test file clean.

## Verification

- `pytest tests/test_worker_faults.py tests/test_worker_state.py`: 16 passed
  (foreground). Only the touched test files were run, as instructed; the full
  suite is the coordinator's.
- `python scripts/check_test_private_imports.py`: 0 new (117 current, 118
  baselined; the one stale entry is in `tests/test_review_round6_evidence.py`,
  not this leaf's).
- Setting `OUTPUT_MARK_SECONDS` to 0 made the earlier throttle test fail
  (checked, then reverted).
- `ruff check` on every touched Python file: clean. An `if` inside `seen` had
  pushed `run` to C901 11, so both flag removals use a comprehension.
- `specy-road file-limits`: OK. `worker_ops.py` was 393 lines before the WIP
  merge and is 400 after it (see the merge note).

## Added

- `FLAG_STALLED` (`worker_state.py`): the flag name, shared by the runner and the sweep.
- `WorkerRecord.last_output_at` (`worker_state.py`): A1's field.
- `OUTPUT_MARK_SECONDS` (`worker_runner.py`): the 5 s write window.
- `run(..., clock=time.monotonic)` keyword (`worker_runner.py`): the public fake-clock boundary for the throttle (R2).
- `_output_seen()` (`worker_runner.py`): throttled `last_output_at` write that also clears `stalled` (A1, A2 clear).
- Guard in `_output_seen`: inside the window, a lock-free `load_record` and an immediate write when the record is flagged `stalled` (R1).
- Reset in the `seen` mutate (`worker_runner.py`): `last_output_at` = launch time and `stalled` dropped at each turn start, so a resumed worker is not judged on the last turn's silence.
- `_output_seen` call inside the existing per-line `try` (`worker_runner.py`): a failed write is logged like a bad line and does not kill the wrapper.
- `sweep_stalled()` (`worker_ops.py`): A2's mark, event and clear-on-leave-running; `now=` is the fake-clock seam.
- Guard in `sweep_stalled`: an unreadable pinned config still uses the default threshold.
- Call in `worker_reconcile.sync` after `sweep_dead_wrappers`, and in `worker_cli.cmd_list` before listing (A2's two commands).
- `stall_after_seconds: 600` in `DEFAULT_POLICY` (`orchestration_config.py`): A3.
- Schema: `last_output_at` and flag `stalled` in the record schema, type `stalled` in the event schema (A3).
- `policy.stall_after_seconds` in the orchestration schema template: lets the documented key be set.
- Test `test_last_output_at_is_written_at_most_every_five_seconds`: A1 throttle through `run(clock=...)`, asserting the persisted time.
- Test `test_a_new_turn_resets_last_output_at_and_the_stalled_mark`: the turn-start reset, bounded by times taken around `run()`.
- Test `test_a_silent_running_worker_is_flagged_once_per_silence`: A2 threshold, one event per silence, clear on leaving `running` for `idle`, `failed` and `terminated`, with `now=`.
- `sweep_stalled` reads all records, not only active ones (round 3 R1): a closed worker must not keep the flag.
- Test `test_output_clears_a_stall_shorter_than_the_write_window`: R1, the line after a stall clears it under a 1 s threshold, a later silence re-raises it, measured from that line; real stdout through `run()` with a sweeping thread.
- Test `test_list_and_sync_flag_a_live_silent_worker`: A2 through `worker list` and `worker sync` on a live spawned wrapper.
- Test `test_policy_stall_after_seconds_overrides_the_default`: a committed `stall_after_seconds: 60` flags at 60 s, not 600.
- Test helpers `PACED_LINES`/`_paced` (harness printing a line after each pause), `_since_launch`, `_stall_repo` (committed `stall_after_seconds`), `_stalled`: support for the tests above.
- Mocks: none. The fake clock is `run`'s `clock` argument and the sweep's `now=`.
