# Implementation summary: M22.16 (reviewer-run-summary-and-process-tree)

## What changed

- **D15c (A1).** `review_record_write.refusal_summary(said, node_id, model)` builds the one-line refusal reason:
  `rerun requested: review record refused the output: <first offending line, whole> (N more; full text in
  work/reviews/<ID>/REJECTED-<model>.md)`. The first offending line is the first indented `where: text` line of
  `review record`'s output (`approve_defect_problem`'s format); a refusal with none (wrong commit, signing) uses its
  first line. `file_review` uses it for the initial refusal (the immediate repair's reason carries that, plus the
  repair turn's own `file_review` reason), and `_delegate_locked` uses it for the stored refusal of a resumed repair,
  replacing both `[-400:]` cuts. `Outcome.refusal` still keeps the whole text.
- **D17 (A2).** `review_delegate._file` passes `Rerun("")` instead of parsing when the last attempt has
  `capacity: true`. The write tripwire and model check still run in `file_review`; the run closes `incomplete` with
  the capacity reason alone. `_repair` no longer wraps an empty reason with `"<first>; after the repair turn, "`,
  so a repair turn ending in capacity also has the capacity reason alone (the refusal stays in `run["refusal"]` and
  REJECTED-<model>.md).
- **D18 (A3).** Both runners (`run_logged`, `delegate_turn`) launch with `start_new_session=True` and read output
  through `reviewer_output(proc)`: a waiter thread reaps the direct child (watched apart from stdout EOF), a reader
  thread queues lines. When the child exits, or the block exits early (KeyboardInterrupt, an exception while
  processing output), `worker_process.end_group(pgid)` sends SIGTERM, SIGKILL after 5 s, then the remaining output is
  drained for at most 5 s. `end_group` is split out of `_end_group`: it signals only while `ps` lists a member, never
  `os.getpgrp()` or pgid <= 1, treats ProcessLookupError as success. `kill_group` passes `confirmed=True` (it just
  verified a member), so its identity checks and first-signal behaviour are unchanged.
- Docs: `docs/orchestration-reviewer-output.md` (summary shape, capacity reason, process group). CHANGELOG
  `[Unreleased]` Fixed.

## Touch zones

Final list unchanged: specy_road/review_record_write.py, specy_road/review_delegate.py, specy_road/worker_process.py,
tests/test_review_run_lows_rc5.py, docs/orchestration-reviewer-output.md, CHANGELOG.md. No change outside them.

## Verification

- `pytest -n 4 tests/test_review_run_lows_rc5.py`: 10 passed. Red-green: with the package changes reverted, 9 of 10
  fail (the "leaves nothing" row passes on both sides by design).
- Full suite `pytest -n 4`: 6545 passed (before the complexity refactor of `reviewer_output`; related files re-run
  after it, 171 passed). `specy-road file-limits` OK; `ruff check` on changed files clean.
- Net lines: package about +125 (estimate +35, informational), tests +155, docs +15.

## Notes for reviewers

- The interrupt tests set SIGINT to `signal.default_int_handler` for the test and have the fake reviewer send SIGINT
  to the test process's pid (the caller), not to itself.
- A process that left the group with `setsid` before the reviewer exited is not reached (out of scope per the plan).

## Added

- `review_record_write.refusal_summary`: the one formatter for the initial, immediate-repair and resumed-repair
  refusal summaries (A1).
- `review_record_write.reviewer_output`, `_group_lines`, `_read_into`, `GROUP_GRACE`, `DRAIN_BOUND`, `_EOF`: watch
  the direct child apart from EOF, end the group on exit, interrupt or error, bounded drain (A3).
- `start_new_session=True` on both runners' Popen (A3).
- `worker_process.end_group` (with `confirmed`): pgid-level SIGTERM/SIGKILL split out of `_end_group`; guard that it
  signals only while the group has a member and never the caller's group (A3).
- `review_delegate._file` branch: `Rerun("")` when the last attempt had a capacity error (A2).
- `review_delegate._repair` guard `and filed.reason`: no first-refusal wrap around an empty capacity outcome (A2).
- tests/test_review_run_lows_rc5.py: refusal summary on immediate and resumed repair (initial checked as the head of
  both) and through `prompt --run`; capacity on initial and repair turns; background child ended through each
  runner; interrupt through each runner; no signal when the reviewer leaves nothing (with a caller-group helper still
  alive). Mocks: `GROUP_FAKE` reviewer script, and `os.killpg` wrapped (still calling through) to assert no signal.
