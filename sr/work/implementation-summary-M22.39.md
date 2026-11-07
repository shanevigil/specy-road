# Implementation summary — M22.39 (worker-stall-recovery)

**Status: blocked on a path outside the touch zones** (see "Blocker"). The code, tests, docs and CHANGELOG
below are committed; READY is not written because the full suite fails on the CLI-surface goldens.

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

All edits are inside the listed zones, plus the out-of-zone goldens below that are still needed:
`specy_road/worker_ops_slots.py`, `specy_road/bundled_scripts/worker_cli.py`, `specy_road/bundled_scripts/doctor.py`,
`specy_road/bundled_scripts/grind_session.py`, `specy_road/worker_state.py`,
`specy_road/schemas/worker-record.schema.json`, `tests/test_worker_stall_recovery.py`,
`docs/orchestration-workers.md`, `CHANGELOG.md`. No new module was needed (all files under the 1,000-line cap).

## Blocker

Adding the `worker recover` subcommand changes the CLI surface, so these fail:
`tests/parity/test_command_surface.py::test_inventory_matches_golden_both_ways`,
`::test_help_transcript_matches_golden[specy-road worker]`, `::test_every_current_name_has_a_golden_transcript`.
The fix is regenerating the goldens (`SPECY_ROAD_PARITY_REGEN=missing` / full regen), which writes
**`tests/parity/golden/inventory.json`**, **`tests/parity/golden/help/specy-road__worker.txt`** and the new
**`tests/parity/golden/help/specy-road__worker__recover.txt`** — all outside this leaf's touch zones. Add them to
the zones and the leaf can finish. Everything else passed: full suite `3 failed, 6826 passed, 8 skipped`
(`pytest -n 4`), the 3 being these.

## Added

- `worker_state.FLAG_NEEDS_PERSON` / schema flag `needs_person` — marks a worker past its recovery limit so it shows in list/status and is not retried.
- `WorkerRecord.recoveries` / schema property — the persisted count, so separate `recover` processes share one limit.
- `worker_ops_slots.DEFAULT_RECOVERIES` — the limit when `policy.max_fix_rounds` is unset (recovery must be bounded).
- `worker_ops_slots._LAUNCH_EVENTS` — events that anchor silence for a worker with no `last_output_at`.
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
- Tests (`tests/test_worker_stall_recovery.py`): `test_a_worker_that_never_wrote_output_is_flagged_from_its_launch` (no output at all; list and doctor show seconds silent); `test_recover_ends_a_stalled_worker_keeps_its_work_and_resumes` (busy worker left running, sync shows the stall, recovered worker keeps commit and uncommitted file, count 1); `test_recover_past_the_limit_stops_as_needing_a_person` (persisted limit from `max_fix_rounds`, last output named, one event, grind's `recover_stalled` path, not retried); `test_recover_refuses_while_another_worker_holds_the_leaf`.
