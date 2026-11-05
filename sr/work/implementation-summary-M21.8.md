# Implementation summary: M21.8 (`queue-message-test-waits-for-idle`)

## Touch zones (confirmed)

- `tests/test_worker_queue_message.py` — test poll fix; no other Python modules import this test module.
- `sr/planning/M21.8_queue-message-test-waits-for-idle_9a94e9ff-94d7-4166-bb4a-fbe6ba5d6daf.md` — fix round: A3 requires verification on this sheet’s checklist, not only in this summary.

## What changed

`test_message_while_running_queues_and_delivers` now leaves its 30-second poll only when there are at least two `completion` events **and** `load_record(...).state != "running"`. A comment documents that `worker_runner._finish` calls `exit_event` (which appends `completion`) before `_exit_state` clears `running` → `idle`, so under load the old exit condition could observe two completions while the record was still `running` and then fail `assert final.state == "idle"`.

All existing assertions after the poll are unchanged.

## Acceptance

- **A1:** Poll waits for second completion and non-`running` record; assertions on `queued_message`, `idle`, events, and prompt file unchanged.
- **A2:** Test-only change; root-cause comment added; no assertions removed.
- **A3:** Twenty consecutive passes recorded below (brief caps `-n auto` to `-n 4` on a shared machine; background CPU load via `stress-ng --cpu 4` when available, else a busy loop).

### A3 verification (2026-11-05)

Command (from git root):

```bash
stress-ng --cpu 4 --timeout 600s & LOAD_PID=$!
FAIL=0
for i in $(seq 1 20); do
  pytest tests/test_worker_queue_message.py::test_message_while_running_queues_and_delivers -q -n 4 || { FAIL=1; break; }
done
kill "$LOAD_PID" 2>/dev/null
exit $FAIL
```

Result: runs 1–20 all passed (`1 passed` each); exit 0. The same evidence is copied to the planning sheet checklist (fix round after review block on A3).

## Probes

- Planning sheet checklist vs acceptance A3 — all three items were unchecked while summary held A3 only; updated sheet with checked boxes and 20-run record — fixed.
- Other M21.8 planning artifacts — only this sheet; no duplicate checklist elsewhere.
- `test_two_cli_messages_during_a_live_turn_are_appended_and_delivered` — still polls on completion count only; acceptance A1 names only `test_message_while_running_queues_and_delivers`; left unchanged.
- Post-merge `tests/test_worker_queue_message.py` poll fix — still present after `origin/WIP/improvements-0-3-1` merge — unchanged.

## Added

- none (poll condition and comment only; no new helpers, mocks, or tests)
