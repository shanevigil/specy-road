# Implementation summary: M22.6 — queued message that cannot be delivered

Branch `feature/rm-queued-message-undelivered`. Base `c65256c16230ee32426b2721d307bb1d72b1655a`.

## What changed

- **A1.** `deliver_queued_message` treats any exception from `_send` as a failed delivery. Unless the worker is already `terminated`, it puts the full text back and sets `message_undelivered` (`FLAG_UNDELIVERED`). It still logs one `error` event, `queued message not delivered: <cause>`, and re-raises. A terminated worker still drops the text and does not gain the flag. `_deliver_queued` swallows that exception, so the wrapper still returns the turn's exit code.
- **A2.** The flag is a value on the existing `flags` list. `worker list`, `worker status`, `worker sync` and `handoff status --json` already print that list. No renderer and no new field.
- **A3.** On the launch path, a stored `queued_message` is sent first, then a blank line, then the turn's own prompt, in the one prompt file. Both the text and the flag are cleared only after `spawn` returns, so a refusal before that (lease, usage limit, slot, launch check, prompt write) keeps both. Delivery clears `queued_message` before it calls `_send`, so the text is not sent twice. A message during a live turn still appends. `terminate` still drops the text and now clears the flag. No new CLI option.
- **A4.** `tests/test_worker_queue_message.py` has one table through the public worker operations and CLI. Delivery after a fake turn is refused by a remote that rejects the lease, by a `generic` harness (resume is unsupported), and by a `work/prompt-…md` path that is a directory (the write raises `OSError`). Each leaves the text, the flag on `worker list --json`, `worker status --json` and `handoff status --json` `workers[].flags`, one error event, and wrapper exit 0. `worker message --text B`, `worker resume` and `worker resume --ready-only` then write one prompt of the stored text, a blank line and their own prompt, and clear both. A resume while the lease is still rejected keeps both. Two messages sent while a turn runs stay in order when delivery is then refused. `terminate` clears both. `docs/orchestration-workers.md` (flags, `queued_message`, message and terminate rows) and a `CHANGELOG.md` `[Unreleased]` Fixed entry record it.
- The existing race `test_deliver_and_message_launch_one_turn` still requires exactly one launch. Its queue check now matches the new rule: if `message` launched, the prompt holds both texts and the queue is empty; if delivery launched, the prompt is the queued text and the message is queued behind it.

## Touch zones

`specy_road/worker_runner.py`, `specy_road/worker_ops_message.py`, `specy_road/worker_ops_lifecycle.py`, `specy_road/worker_state.py`, `specy_road/schemas/worker-record.schema.json`, `tests/test_worker_queue_message.py`, `docs/orchestration-workers.md`, `CHANGELOG.md`.

Confirmed against the call sites. List, status, sync and handoff status already render `flags` from the record, so no file outside this list changed.

## Verification

- `python -m pytest tests/test_worker_queue_message.py -n 4 -p no:cacheprovider -q`: 15 passed.
- `test_deliver_and_message_launch_one_turn` passed 15 times on its own.
- `ruff check` on the touched Python files: all checks passed. `specy-road file-limits`: OK (existing hard-alert warnings on other files only). Clone, private-import and machine-path checks: no new findings.

## Added

### Helpers

- `_prompt_with_queued` (`worker_ops_message.py`): builds `stored + blank line + text` so `_send` stays within the complexity gate.
- `_clear_delivered` (`worker_ops_message.py`): clears `queued_message` and `message_undelivered` only after `spawn` returns, for the same reason.
- `_reject_leases` (test): update hook that refuses lease ref pushes, so the test does not import a private helper.
- `_block_prompt_writes` (test): makes the delivery prompt path a directory so the write raises `OSError`.
- `_deliver_fail` (test): one fake turn with a queued follow-up, and the wrapper's exit code.
- `_flags` (test): the flag is present in `worker list --json`, `worker status --json` and `handoff status --json`.
- `_stuck` (test): the text is still stored, there is one error event, and `_flags` holds.
- `_prompt_text` (test): the one prompt file written for a kind.
- `_two_while_running` (test): two messages during a live turn, then a refused delivery, kept in order.

### Branches or guards

- `deliver_queued_message` except `Exception`: restore the text and set `FLAG_UNDELIVERED` unless the worker is `terminated`, then log and re-raise. A non-`WorkerError` from `_send` used to escape the wrapper.
- `_deliver_queued` except `Exception`: the recorded failure does not change the wrapper's exit code. Previously only `WorkerError` was swallowed.
- `_terminate_locked`: clear `FLAG_UNDELIVERED` when it is set. `terminate` already dropped the text.
- `test_deliver_and_message_launch_one_turn`: the two legal outcomes of the race under the new launch rule (message took the queued text, or delivery launched and the message queued).

### Mocks

- none

### Tests

- `test_undelivered_queued_message`: one table for the refused deliveries, the next message, resume and `resume --ready-only`, a resume that is refused again, two queued messages kept in order, and terminate.
