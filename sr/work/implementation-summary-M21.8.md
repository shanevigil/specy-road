# Implementation summary: M21.8 (`queue-message-test-waits-for-idle`)

## Touch zones (confirmed)

- `tests/test_worker_queue_message.py` — only file changed; no other Python modules import this test module.

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

Result: runs 1–20 all passed (`1 passed` each); exit 0.

## Added

- none (poll condition and comment only; no new helpers, mocks, or tests)
