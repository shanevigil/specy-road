# Implementation summary: M11.2 `resume-failed-workers`

## What changed

`worker message W` and `worker resume W` (both `worker_ops._send`) now reopen a
**failed** worker whose record holds a `provider_session_id`, through the same
adapter resume path an `idle`/`completed` worker uses, instead of refusing with
"delegate again instead".

- **A1.** `terminated` is still refused, and so is `failed` with no session id:
  `w-0001 is failed, session none; delegate again instead`. A **stalled** worker
  is a `running` record with the `stalled` flag. If its wrapper and harness are
  gone (the field case: a harness that never exited, stopped by hand), the
  existing `_wrapper_gone` sweep at the top of `_send` records it as `failed`.
  It then resumes like any other failed worker. If its process is still alive,
  it is still refused, because a live one-shot turn cannot be steered. The
  refusal now says that once the harness exits, `message` resumes the session,
  and that `terminate` closes the worker for good.
- **A2.** Reopening a `failed` worker calls the same `_slot_or_existing` check
  `delegate` uses, under the workers lock `message`/`resume` already hold:
  - more than `max_workers` active gives the same "N workers active, policy
    max_workers is M" refusal;
  - another active worker on the leaf (for example a later delegate) is refused
    with "… already has an active worker (w-…); w-… stays failed".

  In `docs/orchestration-workers.md`, the `resume W` row now lists which states
  can be resumed (`idle`, `completed`, `failed` with a session id) and which are
  refused, with the reasons (`failed` without one, `terminated`, `handed_off`, a
  live process including `stalled`). The `state` row points to it.
- **A3.** `tests/test_worker_resume_failed.py` covers failed with a session id
  (resumes, same session), failed without one (refused with the hint), the
  `max_workers` slot and leaf checks, and both stalled cases.

## Existing tests changed (acceptance reverses what they asserted)

Three tests asserted the old refusal that A1 reverses. They now assert the new
behaviour, and none was deleted:

- `tests/test_worker_faults.py::test_a_killed_harness_leaves_the_worker_failed`: a
  SIGKILLed harness's failed worker (`s-killed` session) now resumes to `idle`
  (it was "is failed; delegate again instead"). The module docstring is updated.
- `tests/test_worker_review_round2.py::test_a_completed_worker_takes_a_review_block_as_a_message`:
  the closed-state loop now checks `terminated` only; failed-with-session is
  covered in the new file.
- `tests/test_review_round5.py::test_a_crashed_running_worker_cannot_be_handed_off_or_messaged`
  is renamed `…_cannot_be_handed_off_and_is_recorded_failed_before_a_message`.
  The `handoff` refusal is unchanged; `message` now records the crash (`error`
  event) and then resumes the session.

## Touch zones (confirmed)

`specy_road/worker_ops.py`, `docs/orchestration-workers.md` and `tests/` were
changed. `specy_road/bundled_scripts/worker_cli.py` needed no change, because
`cmd_message`/`cmd_resume` only forward to `ops.message`/`ops.resume`.

`worker_ops.py` sat at the 400-line cap. To fit, I removed its `CLOSED_STATES`
alias (now unused there; `worker_lease.py` keeps its own) and the
`TERMINAL_STATES` import. The file is at 400 lines.

## Verification

- `pytest`: the whole suite, run in four foreground chunks, all passed: the
  worker/review chunk 175 passed; the three remaining chunks 939, 769 (2
  skipped) and 873 passed. The second chunk first failed
  `test_lean_gates.py::test_private_imports_pass_on_committed_baseline` because
  the new test patched `ops._wrapper_gone`. It now patches the public
  `ops.wrapper_gone` instead, and the baseline is unchanged.
- `specy-road file-limits`: OK.
- `ruff check specy_road/worker_ops.py tests/test_worker_resume_failed.py`: clean
  (C901).

## Added

### Helpers
none

### Branches or guards
- `_send`: a `terminated` record, or a `failed` one without `provider_session_id`, is refused with "delegate again instead". This replaces the blanket closed-state refusal, so failed-with-session falls through to resume (A1).
- `_send`: the `process_alive` refusal adds a stalled-specific hint when `FLAG_STALLED` is set, so the coordinator knows the session resumes once the harness exits and that `terminate` would close it for good (A1, the stalled case).
- `_send`: a `failed` record takes a `max_workers` slot via `_slot_or_existing` and is refused while another worker holds the leaf (A2).

### Mocks
- `test_a_stalled_worker_that_is_still_alive_says_how_to_resume` patches `ops.wrapper_gone` → False and `ops.process_alive` → True, to stand in for a live, silent harness without spawning one.

### Tests
- `test_message_resumes_a_failed_worker_with_a_session_id`: A1/A3. CLI `message` on a failed worker with a session id resumes the same session and ends `idle`.
- `test_a_failed_worker_without_a_session_id_is_still_refused`: A1/A3. CLI `message` and `ops.resume` refuse with the hint, and the record stays `failed`.
- `test_a_terminated_worker_with_a_session_id_is_still_refused`: `terminate` still closes a worker for good.
- `test_a_stalled_worker_whose_process_ended_resumes`: A1 stalled. A stalled `running` record with no live process is recorded `failed`, then resumed.
- `test_a_stalled_worker_that_is_still_alive_says_how_to_resume`: A1 stalled. A live stalled worker is refused, and the refusal explains how to resume it.
- `test_the_reopened_turn_counts_against_max_workers`: A2. Refused while the one slot is held; resumes once the slot frees.
- `test_a_leaf_already_held_by_another_worker_is_not_reopened`: A2. A failed worker is not reopened over a newer worker on the same leaf.
