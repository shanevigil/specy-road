# Implementation summary: M11.56 — reviews dir before launch

## What changed

- `specy_road/worker_ops.py`: the main checkout's `work/reviews/<ID>` (`reviews_dir`) is created with
  `mkdir(parents=True, exist_ok=True)` right before `adapter.launch(...)` in `_launch_locked` (delegate)
  and right before `adapter.resume(...)` in `_send` (message and resume). The calls are inline, not a
  helper, because the file is at the 400-line limit. Every
  default or custom command that names the directory (`--add-dir`, `{reviews_dir}`) is built after it
  exists, on every adapter, so a freshly picked leaf with no review files launches on Cursor too.
- `tests/test_worker_m310_reconcile_status.py`: `nested_project` takes an optional `roster` so a test can
  roster default-command harnesses (no `channels.cli`). The default behaviour is unchanged.
- `tests/test_worker_reviews_dir_before_launch.py` (new): delegates a fresh leaf into a linked worktree on
  the Cursor adapter (`agent`) and on Claude Code (`claude`). Both run their default commands against fake
  binaries on `PATH` that exit 1 with "Workspace directory does not exist" when an `--add-dir`/`--workspace`
  directory is missing. The test then removes the directory and checks that `message` recreates it before the
  resume.

The directory is created in `worker_ops`, not in the adapters' path helper. Building an argv stays free of
side effects, and the two operations that launch a worker are where the directory is created.

## Touch zones (confirmed)

`specy_road/worker_ops.py`, `tests/`. `specy_road/worker_adapters.py` needed no change.

## Verification

- Red/green: with `worker_ops.py` at the base commit, the new test fails for both `cur` and `cc` (the worker
  ends `failed`, not `idle`). With the fix, both pass.
- The worker test files listed in READY pass, and `specy-road file-limits` passes.

## Added

- Two inline `reviews_dir(...).mkdir(...)` calls in `worker_ops._launch_locked` and `worker_ops._send`: the
  directory exists before any launch or resume argv names it (A1). Helpers and guards: none.
- `nested_project(..., roster=None)` parameter: lets the regression test use default-command harnesses.
- `STRICT` fake harness and `strict_path` fixture: fake `agent`/`claude` binaries that fail like Cursor
  when an allowed directory is missing.
- `test_a_fresh_leaf_launches_and_resumes_with_no_reviews_dir_yet[cur|cc]`: the A1 regression test for
  delegate, plus message/resume.
