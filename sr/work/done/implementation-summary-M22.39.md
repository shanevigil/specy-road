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

## Fix round 2 (gpt-5.6-sol-high block at a5a81abf)

**Findings:**
- A recovery left the old turn's presence session (`<user>-s<old pgid>`) live, so the resumed worker's guard
  saw it as a peer.
- A recovery of a dead wrapper with a live harness returned the new worker still flagged
  `wrapper_gone_harness_alive`.

**Class:** what the ended turn leaves on the record and in presence. `terminate` cleans this up;
`recover`'s own ending step did not.

**Design change:** `recover` ends the turn through one step, `_end_turn`. It mirrors `terminate` except
that it does not close the record:
- it signals the group through `kill_group` when anything in the group lives;
- only after that (`kill_group` raises if the group survives, leaving the flag and the session in place) it
  clears `wrapper_gone_harness_alive` and calls terminate's own `_end_worker_session` for `<user>-s<pgid>`.

No file outside the zones changed. The doc's `recover` row says so.

## Probes (round 2)

- Old turn's presence session `<user>-s<pgid>` in its worktree: ended by `recover`; a peer's session (`<user>-s1`) stays (test). Red without the fix.
- Dead wrapper (SIGKILLed by the test) with a live harness: `sync` flags `wrapper_gone_harness_alive`; `recover` ends the harness by its recorded start time, the old harness pid is gone, and the returned record has no orphan flag and a new pid; the worker resumes to `idle` (test). Red without the fix.
- `kill_group` fails (group survives, or descendants cannot be listed): it raises before the clears, so the flag and the session stay and the error reaches the caller (by reading the code).
- Group already gone (dead wrapper and dead harness): no signal; the stale orphan flag and the session are still dropped, and `_send`'s dead-wrapper close marks the record `failed` with its session, then resumes (by reading the code).
- Other per-turn residue, compared with `terminate`:
  - `queued_message` / `message_undelivered`: kept on purpose, so `_send` delivers the text with the continue prompt and clears both.
  - `descendants_unchecked`: owned by `kill_group`.
  - lease: released by `_send`'s dead-wrapper close and acquired anew.
  - `pid`, `pgid`, `harness_pid`, `harness_start`: reset by `spawn`'s mark and the wrapper.
  - `post_run_findings`: set or cleared by the next turn's check.
  - `needs_reconcile` and `possibly_modified_externally`: about the worker, not the turn, so kept.
- `resume` and `message` of a failed worker: not changed by this leaf. They keep their existing behaviour, which `_send` owns outside these zones.

## Fix round 3 (grok-4.7-high block at d3d9eeb5)

**Findings:**
- An unreachable lease remote left the worker `failed`, counted and unflagged, so `recover --offline`
  answered "not stalled".
- The live turn is signalled before that push.
- `grind-session` repeats the online call.

**Class:** any refusal inside the resume step after the turn has been ended: the lease push, a launch or
config check (the test first hit a missing `origin/HEAD` this way), the slot check, the branch check. Each one
stranded a worker that no later `recover` would touch.

**Ordering:** the turn has to end first. `_send` will not start a turn while the old one lives (it queues or
refuses), and the lease push lives in `_send` (outside the zones). So moving the push earlier is not
possible, and I did not do it.

**Design change: one rule, `recovery_pending`.** A recovery is counted when it ends the turn, and its event
carries `detail.recovery`. It is pending while that event is newer than the worker's last `message` event
(`_send` writes one before every spawn) and the worker is not `terminated`. `recover` finishes a pending
recovery without the stalled check and without counting it again, online or `--offline`:
- `stalled_workers` / `stall_lines` list pending recoveries;
- `worker list` shows them even when no worker is active (a failed worker is not "active");
- grind-session's `recover_stalled` retries them each pass.

The counting is split into `_next_recovery` (limit check and `needs_person`), so `recover` gains no net
branches. Documented limit: a spawn that fails after its `message` is logged counts as started.

## Probes (round 3)

- Unreachable origin (`https://127.0.0.1:1/…` with `origin/HEAD` set): `recover` exits 1 with "cannot reach origin"; the old wrapper is ended; recoveries is 1; `worker list` shows `recovery pending … 1/3`; `recover --offline` exits 0 and resumes to `idle`; recoveries stays 1; afterwards neither stalled nor pending (test). Red without the fix.
- Missing `refs/remotes/origin/HEAD` (a launch/config check after the end): same class, same pending rule (hit while writing the test; covered by the rule).
- A pending recovery whose worker was `terminated`: not pending (excluded by state).
- A pending recovery finished by a manual `worker resume` (it writes `message`): no longer pending (by the rule).
- Grind `recover_stalled`: pending workers are included in `stalled_workers`, so each pass retries them online. While the remote is down it reports `worker_recover_refused` and the recovery stays pending. The docs name `--offline` as the manual way out. I did not add an offline fallback to grind, because it would bypass the global count unannounced.
- `kill_group` failure: raises after the count and event, so the recovery is pending and the next call retries the end. The old turn's flag and presence session are kept until the group is confirmed gone (round 2).
- Another worker delegated (`--rework`) onto the leaf while a recovery is pending: `recover` refuses ("already has an active worker").
- Existing worker, grind (all `test_grind_session*`), doctor, presence and terminate suites: pass.

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
- `worker_ops_slots._end_turn` — ends the stalled turn and drops its orphan flag and presence session once the group is confirmed gone, reusing terminate's `_end_worker_session` (fix round 2).
- `worker_ops_slots.recovery_pending` — a counted recovery whose resume never started, finished by the next call uncounted (fix round 3).
- `worker_ops_slots._next_recovery` — the limit check and `needs_person`, split out of `recover` (fix round 3).
- `stalled_workers` / `stall_lines` `pending` entry and line; `worker list` shows stall lines with no active worker (fix round 3).
- `worker_ops_slots.recover_stalled` (+ no-`work/.workers` guard) — the loop body grind-session calls (A4).
- `worker_cli._with_stalls`, `cmd_recover`, the `recover` parser; `cmd_list`/`cmd_sync` append stall lines — A1/A2.
- `doctor._print_stalled` (+ no-`work/.workers` guard so doctor creates nothing) — A1.
- `grind_session.RECOVER_EVERY`, `_recover_stalled`, calls in `_run_loop` and `_wait_for_signal` — A4.
- Mocks: none.
- `tests/parity/command_map.yaml` rows (recover added; worker parent help) and golden `specy-road__worker__recover.txt`: the parity harness's required way to change the command surface.
- Test (round 3): `test_a_recovery_whose_resume_was_refused_is_finished_by_the_next_call` (distinct regression: unreachable lease remote after the end).
- Tests (`tests/test_worker_stall_recovery.py`, round 2): `_silent_worker` helper shared by the two real-process tests; the recover test now also checks that the old turn's presence session ends and a peer's stays; new `test_recover_ends_a_live_harness_whose_wrapper_died` (distinct regression: dead wrapper with a live harness).
- Tests (`tests/test_worker_stall_recovery.py`): `test_a_worker_that_never_wrote_output_is_flagged_from_its_launch` (no output at all; list and doctor show seconds silent; a follow-up turn's `message` resets silence); `test_recover_ends_a_stalled_worker_keeps_its_work_and_resumes` (busy worker left running, sync shows the stall, recovered worker keeps commit and uncommitted file, returned record unflagged, a second recover refused as not stalled, count 1); `test_recover_past_the_limit_stops_as_needing_a_person` (persisted limit from `max_fix_rounds`, last output named, one event, grind's `recover_stalled` path, not retried); `test_recover_refuses_while_another_worker_holds_the_leaf`.
