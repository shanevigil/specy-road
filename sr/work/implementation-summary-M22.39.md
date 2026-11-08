# Implementation summary — M22.39 (worker-stall-recovery)

**Status: ready.** Merged `origin/WIP/improvements-0-3-1` first (clean merge); the CLI-surface goldens the
first run stopped on are now in the zones and updated.

## What changed

- **A1 — detection.** `sweep_stalled` measures silence with the new `silent_seconds`: `last_output_at` when set,
  else the turn's latest launch event (`started`, `message`, `resumed`, `launched`), else `created`. A running
  worker that never wrote output is no longer skipped. `stalled_workers` (sweep, then one dict per stalled worker
  with `silent_seconds`, `recoveries`, `recovery_limit`, `needs_person`) and `stall_lines` feed `worker list`,
  `worker sync` (text and `--json` `stalled` list) and `doctor` (report only).
- **A2/A3 — `specy-road worker recover W [--offline] [--op-id] [--json]`.** One shot under the workers lock (so two
  recoveries never overlap). Sweeps, then refuses with nothing ended when: not stalled; another active worker holds
  the leaf; `recoveries` ≥ limit (flags `needs_person`, one `error` event naming the last output, worker left
  running); lease not broker; no resumable native session. Otherwise counts the recovery on the record first,
  logs one `error` event, ends the process group with the existing `kill_group` (record not terminated), and
  resumes through the existing `_send` path with `CONTINUE_PROMPT` (the dead wrapper is recorded `failed` with its
  session; the worktree, commits and uncommitted files are untouched). Limit: `policy.max_fix_rounds`, else 3
  (coordinator resolution: the fix-round policy; the default of 3 when unset is my choice, stated in docs).
- **A4 — grind-session.** `_recover_stalled` runs `recover_stalled` at the start of each `_run_loop` cycle and, in
  manual mode, every 60 s of `_wait_for_signal`'s polling; emits `worker_recovered` / `worker_needs_person` /
  `worker_recover_refused`. Never raises. No-op when `work/.workers/` does not exist.
- **A5.** `tests/test_worker_stall_recovery.py`, `docs/orchestration-workers.md` (flags, `recoveries` field,
  command row, "Stalled workers" section), CHANGELOG `[Unreleased]` entry.

## Touch zones (final)

`specy_road/worker_ops_slots.py`, `specy_road/bundled_scripts/worker_cli.py`, `specy_road/bundled_scripts/doctor.py`,
`specy_road/bundled_scripts/grind_session.py`, `specy_road/worker_state.py`,
`specy_road/schemas/worker-record.schema.json`, `tests/test_worker_stall_recovery.py`,
`docs/orchestration-workers.md`, `CHANGELOG.md`, `tests/parity/command_map.yaml`, `tests/parity/golden/help/`
(`tests/parity/golden/inventory.json` was added to the zones but needed no change). No new module was needed.

## Parity goldens

Per `tests/parity/README.md`: two `command_map.yaml` rows: one adds `specy-road worker recover`, one covers
the parent `specy-road worker`, whose `--help` now lists it. Then `SPECY_ROAD_PARITY_REGEN=missing` wrote the
one missing transcript, `tests/parity/golden/help/specy-road__worker__recover.txt`. The baseline
`inventory.json` and `specy-road__worker.txt` stay as they are; the rows declare the delta.

## Verification

Before the goldens: full suite `pytest -n 4` gave 3 failed (the parity tests above), 6826 passed. After them:
the targeted run below passes, `pytest -m parity tests/parity` passes (180 passed, 1 skipped), ruff is clean,
and `specy-road file-limits` is OK.

## Fix round 1 (gpt-5.6-sol-high block at d17bd24e)

**Finding:** `recover()` resumed the worker but left `stalled` on the record. The record also still held the
old `last_output_at` until the new wrapper wrote its launch time. A second `recover` queued behind the first
re-flagged the fresh turn, ended it and spent another retry.

**Class:** a follow-up turn inherits the previous turn's silence (`last_output_at` and `stalled`) between
`_send`'s `message` event and the new wrapper's first record write. Every path that starts a follow-up turn
through `_send` hits it: `recover`, `resume`, `message`, and the wrapper's queued-message delivery.

**Design change (one rule, `silent_seconds`):** silence runs from the newest of `last_output_at` and the
`message` or `resumed` event that started the current follow-up turn. With neither, it runs from the first
turn's `started`/`launched` event, else `created`. This replaces the earlier `_LAUNCH_EVENTS` fallback, so
no branch is added. `recover` also clears `stalled` in the same mutate that counts the recovery, so the
record it returns is not flagged. Docs state the rule.

## Probes

- `recover` twice in a row against a live wrapper, with `last_output_at` set back to OLD between the calls (the window before the new wrapper writes): the second call is refused as "not stalled" and does not end the fresh turn or spend a retry (test).
- Record returned by `recover --json`: no `stalled` flag (test).
- Rule clause: a `message` event newer than an old `last_output_at` gives 0 s of silence and clears `stalled`; 5 s later it reads 5 (test).
- `resume` and `message` (both through `_send`, which writes `message` before `spawn`): covered by the same rule; no separate code.
- Queued delivery (the runner calls `_send`, which writes `message`): covered by the same rule.
- A `message` text queued while a turn runs writes `message_queued`, not `message`, so it does not reset a live turn's silence: checked in `queue_worker_message`.
- `grind-session` `recover_stalled`: each `recover` sweeps again under the lock, so a worker its list named but another recovery already resumed is refused, not ended: by the same rule.
- First turn (no `message` event): unchanged. The existing `test_worker_faults` stall tests and the never-output test pass.
- Red-green: with the `worker_ops_slots.py` change reverted, both new clauses fail (`stalled_workers` lists the resumed worker; the returned flags contain `stalled`). With it, they pass.

## Added

- `worker_state.FLAG_NEEDS_PERSON` / schema flag `needs_person` — marks a worker past its recovery limit so it shows in list/status and is not retried.
- `WorkerRecord.recoveries` / schema property — the persisted count, so separate `recover` processes share one limit.
- `worker_ops_slots.DEFAULT_RECOVERIES` — the limit when `policy.max_fix_rounds` is unset (recovery must be bounded).
- `worker_ops_slots._TURN_EVENTS` / `_FIRST_EVENTS` — the events that start a follow-up turn and the first turn; silence never runs from before them (fix round 1).
- The `stalled` flag cleared in `recover`'s counting mutate, so the returned record is not flagged (fix round 1).
- `worker_ops_slots._policy` — shared pinned-policy read for the stall window and the limit.
- `worker_ops_slots.silent_seconds` — silence from last output, or from launch when none (A1).
- `worker_ops_slots.last_output` — last harness-parsed summary, named in stall and needs-person messages (was inline in `sweep_stalled`).
- `sweep_stalled` branch clearing `needs_person` with `stalled` — a worker that speaks again is no longer waiting for a person.
- `worker_ops_slots.stalled_workers` / `stall_lines` — one report for list, sync and doctor with seconds silent (A1).
- `worker_ops_slots.recovery_limit` — `policy.max_fix_rounds` or the default (A3).
- `worker_ops_slots.recover` and its guards (not stalled, other live worker on the leaf, limit, writer, resumable session, branch) — A2/A3.
- `worker_ops_slots.recover_stalled` (+ no-`work/.workers` guard) — the loop body grind-session calls (A4).
- `worker_cli._with_stalls`, `cmd_recover`, the `recover` parser; `cmd_list`/`cmd_sync` append stall lines — A1/A2.
- `doctor._print_stalled` (+ no-`work/.workers` guard so doctor creates nothing) — A1.
- `grind_session.RECOVER_EVERY`, `_recover_stalled`, calls in `_run_loop` and `_wait_for_signal` — A4.
- Mocks: none.
- `tests/parity/command_map.yaml` rows (recover added; worker parent help) and golden `specy-road__worker__recover.txt`: the parity harness's required way to change the command surface.
- Tests (`tests/test_worker_stall_recovery.py`): `test_a_worker_that_never_wrote_output_is_flagged_from_its_launch` (no output at all; list and doctor show seconds silent; a follow-up turn's `message` resets silence); `test_recover_ends_a_stalled_worker_keeps_its_work_and_resumes` (busy worker left running, sync shows the stall, recovered worker keeps commit and uncommitted file, returned record unflagged, a second recover refused as not stalled, count 1); `test_recover_past_the_limit_stops_as_needing_a_person` (persisted limit from `max_fix_rounds`, last output named, one event, grind's `recover_stalled` path, not retried); `test_recover_refuses_while_another_worker_holds_the_leaf`.
