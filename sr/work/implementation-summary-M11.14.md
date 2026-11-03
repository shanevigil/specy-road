# Implementation summary: M11.14 — queue-worker-message

## What changed

- **`worker message` while a turn is running** stores the text on `WorkerRecord.queued_message` (under the workers lock), logs `message_queued`, and returns without spawning. **`--no-queue`** restores the previous “cannot steer a live turn” refusal (including the stalled hint).
- **After each turn**, the wrapper calls `deliver_queued_message`, which clears the queue and runs the normal resume/`_send` path; delivery failures re-queue and log a system `error`.
- **`worker terminate`** clears `queued_message` and notes `dropped queued follow-up` on the `terminated` event.
- **`worker list` / `sync`** show queued text (`_line`, `sync_worker_header`); JSON sync payloads include `queued_message` when set.
- **Docs** (`docs/orchestration-workers.md`) document the field, event type, commands, and terminate behaviour.

## Touch zones (confirmed)

Listed in the brief, plus **`specy_road/bundled_scripts/worker_cli_render.py`**, **`specy_road/schemas/worker-record.schema.json`**, and **`specy_road/schemas/worker-event.schema.json`** (required for record/event validation and list/sync rendering).

## Verification

- `pytest tests/test_worker_queue_message.py tests/test_worker_resume_failed.py tests/test_review_round4_sol.py::test_concurrent_messages_launch_one_turn`
- `specy-road file-limits`

## Added

- `WorkerRecord.queued_message` — holds a follow-up until delivery or terminate.
- `_send(..., no_queue=)` branch — refuses a live turn when `no_queue`, else delegates to `queue_worker_message`.
- `queue_worker_message` in `worker_runner.py` — writes the queue under lock and appends `message_queued`.
- `deliver_queued_message` in `worker_runner.py` — pops the queue and resumes via `_send`; re-queues on `WorkerError`.
- `_deliver_queued` in `worker_runner.py` — invoked from `_exit_state` after each turn.
- Terminate guard on `queued_message` — clears queue and extends the terminated summary.
- `--no-queue` on `worker message` CLI — opt out of queueing.
- `sync_worker_header` in `worker_cli_render.py` — sync/list-style queued line plus JSON field.
- `message_queued` event type in `worker-event.schema.json`.
- `tests/test_worker_queue_message.py` — queue, delivery, list/sync, terminate, and `--no-queue` coverage.
- Updates to `test_worker_resume_failed.py` and `test_review_round4_sol.py` — `--no-queue` / concurrent queue expectations.
