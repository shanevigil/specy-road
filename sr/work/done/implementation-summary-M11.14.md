# Implementation summary: M11.14 — queue-worker-message

## What changed

- **`worker message` while a turn is running** stores the text on `WorkerRecord.queued_message` (under the workers lock), logs `message_queued`, and returns without spawning. A second message during the same turn is appended, separated by a blank line; the event summary says `appended`. **`--no-queue`** restores the previous “cannot steer a live turn” refusal (including the stalled hint). **`resume()`** always passes `no_queue=True` into `_send`, so a live process is still refused.
- **After each turn**, the wrapper calls `deliver_queued_message`, which holds `workers_lock` across `_send` (same scope as `message()`), so liveness and spawn are one transition; on `WorkerError` it re-queues only when the refreshed record is not `terminated`.
- **`worker terminate`** clears `queued_message` and notes `dropped queued follow-up` on the `terminated` event.
- **`worker list` / `sync`** show queued text; JSON sync payloads include `queued_message` when set. The list/sync test reads that through the public CLI, not a private renderer.
- **Docs** (`docs/orchestration-workers.md`) document the field, event type, commands, and terminate behaviour.

## Touch zones (confirmed)

Listed in the brief, plus **`specy_road/bundled_scripts/worker_cli_render.py`**, **`specy_road/schemas/worker-record.schema.json`**, and **`specy_road/schemas/worker-event.schema.json`** (required for record/event validation and list/sync rendering).

## Verification

- `pytest tests/test_worker_queue_message.py tests/test_worker_resume_failed.py tests/test_review_round4_sol.py::test_concurrent_messages_launch_one_turn tests/test_review_round6_runner.py::test_a_dead_wrapper_with_a_live_harness_keeps_the_leaf_and_terminate_kills_the_group`
- `python scripts/check_test_private_imports.py`
- `specy-road file-limits`

## Added

- `WorkerRecord.queued_message` — holds a follow-up until delivery or terminate.
- `_send(..., no_queue=)` branch — refuses a live turn when `no_queue`, else delegates to `queue_worker_message`.
- `resume()` → `_send(..., no_queue=True)` — keeps the live-process refusal; only `message` queues.
- `queue_worker_message` in `worker_runner.py` — writes the queue under lock (appends to an existing follow-up with a blank line) and logs `message_queued` (`queued:` or `appended:`).
- `test_two_cli_messages_during_a_live_turn_are_appended_and_delivered` — two CLI messages during one live turn are delivered in order.
- `deliver_queued_message` in `worker_runner.py` — pops the queue and resumes via `_send` under `workers_lock`; re-queues on `WorkerError` only if not terminated.
- `test_deliver_and_message_launch_one_turn` — concurrent `deliver_queued_message` and `message` launch one turn.
- `_deliver_queued` in `worker_runner.py` — invoked from `_exit_state` after each turn.
- Terminate guard on `queued_message` — clears queue and extends the terminated summary.
- `--no-queue` on `worker message` CLI — opt out of queueing.
- `sync_worker_header` in `worker_cli_render.py` — sync/list-style queued line plus JSON field.
- `message_queued` event type in `worker-event.schema.json`.
- `tests/test_worker_queue_message.py` — queue, delivery, list/sync via public CLI, terminate, and `--no-queue` coverage.
- Updates to `test_worker_resume_failed.py` and `test_review_round4_sol.py` — `--no-queue` / concurrent queue expectations; stalled-alive now asserts the stalled hint on `message(..., no_queue=True)` and that `resume()` still refuses.
