# Implementation summary: M3.10 — Worker hand-off, reconcile and finish report what actually happened

## Goal

Delegated workers can write READY from linked worktrees, reconcile reports real deviations only, sync/list surface harness outcomes, handoff status distinguishes executor verify from reviewer re-runs, and merge-mode finish states what it will push.

## Acceptance

| ID | Done | How |
|---|---|---|
| A1 | yes | `ClaudeCode._add_dir` passes `--add-dir` to `reviews_dir` when `linked_worktree`; docs note Codex/Cursor equivalents |
| A2 | yes | Reconcile normalizes zones with `_clean`; `contract_changed` ignores prompt hash drift when `_brief_unchanged` |
| A3 | yes | `review_cli._executor_verify_problems` labels READY verify; review lines show `commands_rerun` |
| A4 | yes | Codex agent messages and generic output keep the full text in `detail.message`; sync prints it when READY is absent, looking back through the whole event log (the message may have been acknowledged before the exit event) to the previous turn's exit |
| A5 | yes | `print_merge_push_notice` before the first merge land and again in `retry_merge_landing` |
| A6 | yes | Generic, Claude, Codex and Cursor error results keep the full harness text in `detail.message` for sync and list |

## Touch zones (confirmed)

`specy_road/worker_adapters.py`, `specy_road/worker_ops.py`, `specy_road/worker_reconcile.py`, `specy_road/bundled_scripts/review_cli.py`, `specy_road/bundled_scripts/worker_cli.py`, `specy_road/finish_land_integration.py`, `specy_road/bundled_scripts/finish_task.py`, `specy_road/bundled_scripts/finish_task_args.py`, `docs/orchestration-workers.md`, `tests/` — no additions; `finish_modes.py` was not listed but only re-exports a call to `finish_land_integration.print_merge_push_notice` (would have duplicated merge notice logic in `finish_task.py` otherwise).

## Verification

```bash
pytest tests/test_worker_m310_reconcile_status.py tests/test_review_evidence.py tests/test_worker_adapters.py -q
```

## Added

- `linked_worktree` / `_reviews_handoff_dir` in `worker_adapters.py` — detect linked worktrees and resolve main-checkout review hand-off dir for `--add-dir`
- `ClaudeCode._add_dir` — append `--add-dir` on default launch/resume in linked worktrees only
- Harness `detail.message` on Claude, Cursor, Codex agent messages and errors, and generic stdout — preserve the full final text for sync/list
- `print_merge_push_notice` call in `finish_modes.retry_merge_landing` — the retry path states the integration push before it lands
- `worker_repo` / `nested_project` in `tests/test_worker_m310_reconcile_status.py` — local setup so the new tests do not import another module's private helpers
- Updated `tests/test_worker_adapters.py` parser assertions — Claude success detail includes `message`, Codex and generic keep the full text
- `_delegated_brief` / `_brief_unchanged` in `worker_reconcile.py` — byte-compare fresh brief to delegated copy
- Zone `_clean` in reconcile — match review-packet directory zones
- `_executor_verify_problems` in `review_cli.py` — executor-reported label on READY verify problems
- `commands_rerun` in handoff status review rows — distinguish reviewer re-runs in rendered output
- `_harness_message_before`, `_sync_event_lines`, `_terminal_message` in `worker_cli.py` — full harness message on sync/list without changing `worker_runner`
- `integration_commits_ahead_of_remote` / `print_merge_push_notice` in `finish_land_integration.py` — pre-merge push notice with ahead count
- `print_merge_push_notice` call in `finish_modes.apply_on_complete_mode` and `retry_merge_landing` — notice before the first land and before a retry land
- `_ends_turn` in `worker_cli.py`, and the stop at it in `_harness_message_before` — sync reads the full log, so the lookback must not cross into an earlier turn; reached by the second exit in `test_sync_shows_an_acknowledged_final_message_with_the_later_exit`
- Full event history passed to `_sync_event_lines` in `cmd_sync` — a final message acknowledged before the exit event is still found (review round 2, Sol)
- `tests/test_worker_m310_reconcile_status.py` — behavioural coverage for A1, A2, A4–A6 and merge help; `test_sync_shows_an_acknowledged_final_message_with_the_later_exit` covers ack-then-completion and ack-then-error through the CLI
- Removed `test_handoff_status_labels_ready_verify_as_executor_reported` (review round 2, Grok) — `tests/test_review_evidence.py::test_status_lists_a_failing_verifier` asserts the same executor-reported problem string
- Updated assertions in `tests/test_review_evidence.py` — executor-reported wording
