# Implementation summary — M10.3 (replace-per-worker-polling-with)

Branch `feature/rm-replace-per-worker-polling-with`, base `4292c1c`. Implementation commit `4841c4d`.

## What changed

- **A1** — `specy_road/worker_state.py` `append_event` now also replaces `work/.workers/FLAG` (constant `MAILBOX_FLAG`) after it saves the record. This happens inside the same workers-lock section as the log append, so every event path (wrapper, sweeps, intervention, CLI) updates the flag. The file is replaced through the existing `_write_atomic`, not just touched: the mtime changes, and the inode changes too, so a filesystem with coarse mtime still shows the change. Its content (`w-NNNN #seq at`) is only a human-readable hint; nothing reads it.
- **A2** — `worker sync --wait [--timeout SECONDS]` (default 600) in `specy_road/bundled_scripts/worker_cli.py`:
  1. Takes `flag_stamp` (`(inode, mtime_ns)`, or `None` before any event) **before** the pending check. An event that lands between the check and the wait therefore still ends the wait.
  2. Runs a plain `ops.sync(root)` (no ack). If any worker has unacknowledged events, it does not wait.
  3. Otherwise calls `wait_for_event(root, timeout, since)`, which stats the flag every 250 ms with `time.sleep`. It uses no OS watch API.
  4. Prints the usual `sync` output with `--ack` honoured. Exit 2 when the wait timed out and the final delta is empty, so the empty delta plus exit 2 is the timeout case.
  - If the final `sync`'s own dead-wrapper or stall sweep finds something at the timeout, it is printed with exit 0, not hidden behind exit 2.
  - The wait can overshoot `--timeout` by up to one 250 ms interval.
- **A3** — The wait is a loop in the calling process; nothing is spawned. A `KeyboardInterrupt` during the pending check or the wait prints `worker sync: interrupted; nothing acknowledged` to stderr and exits 130 with no traceback.
- **A4** — Docs:
  - `docs/orchestration-workers.md`: the quickstart bullet, the loop code block comment, a new **Waiting** paragraph in "The loop", and the `sync` row of the command table.
  - `docs/grind-session.md` step mode: the code-block comment, plus one sentence after the review-ordering paragraph.
  - The module docstring of `worker_cli.py` now lists exit 2 for a timed-out `sync --wait`.

## Deviations from the Approach

- `wait_for_event(repo_root, timeout, since)` and `flag_stamp` live in `worker_state.py`, not `worker_ops.py`. `worker_ops.py` was already at the 400-line file cap, so it could not take the function or even a re-export line without an unrelated trim. The CLI imports both from `worker_state`, which it already imports from. `worker_ops.py` is unchanged.
- The Ctrl-C test lives in `tests/test_worker_state.py` (beside the wait-loop tests) because `tests/test_worker_cli.py` is exactly at the 400-line cap after the CLI wait test.
- Files at the cap after this change: `docs/orchestration-workers.md` and `tests/test_worker_cli.py` are at 400 lines, and `docs/grind-session.md` is at its 500-line override. To fit, the doc additions are long single-line paragraphs or extensions of existing lines, and the CLI test has one `;` line. No limit or exemption was changed.

## Touch zones (final list)

These were edited: `specy_road/worker_state.py`, `specy_road/bundled_scripts/worker_cli.py`, `docs/orchestration-workers.md`, `docs/grind-session.md`, `tests/test_worker_cli.py`, `tests/test_worker_state.py`.

`specy_road/worker_ops.py` is listed but untouched (see Deviations).

Nothing outside the zones needed a change. The only other code that lists `work/.workers/` globs `w-*.yaml`, so the new `FLAG` file does not affect it.

## Verification

- `pytest tests/test_worker_cli.py tests/test_worker_state.py`: 27 passed.
- `pytest tests/test_worker_*.py tests/test_prerelease_workers.py`: 119 passed.
- `specy-road file-limits`: OK.
- `ruff check` on the four changed Python files: all checks passed.
- Mutation check: with the FLAG write replaced by `pass`, the three new A1/A2 tests fail. The file was restored before the commit.
- The full `pytest` suite was not run; only the worker tests were (about 7 minutes).

## Added

- `MAILBOX_FLAG` constant (`worker_state.py`): names the one mailbox file, `work/.workers/FLAG` (A1).
- FLAG write at the end of `append_event`'s locked section: every event updates the flag's mtime and inode (A1).
- `flag_stamp(repo_root)` (`worker_state.py`): the flag's `(inode, mtime_ns)` or `None`; what the wait compares against (A2).
- `wait_for_event(repo_root, timeout, since, interval=0.25)` (`worker_state.py`): the 250 ms stat loop in the calling process; `True` on a change, `False` at the timeout (A2, A3).
- `--wait` and `--timeout SECONDS` (default 600) on `worker sync` (`worker_cli.py`) (A2).
- In `cmd_sync`, a stamp taken before the pending check: so a race between the check and the wait cannot lose a wake-up (A2).
- In `cmd_sync`, the pending-event short-circuit (`ops.sync(root)` with no ack): returns at once when an unacked event already exists (A2).
- In `cmd_sync`, the `timed_out and not delta` → exit 2 branch: the timeout exit code (A2).
- In `cmd_sync`, the `KeyboardInterrupt` guard → stderr line and exit 130: a clean interrupt with no traceback and no ack (A3).
- Test `test_every_event_replaces_the_mailbox_flag` (`tests/test_worker_state.py`): A1.
- Test `test_wait_for_event_returns_on_the_next_event_or_times_out` (`tests/test_worker_state.py`): A2 at the function level. It covers the timeout, a `threading.Timer` that appends during the wait, and a flag already changed since `since`.
- Test `test_sync_wait_ctrl_c_exits_130_without_a_traceback` (`tests/test_worker_state.py`): A3. It monkeypatches `worker_cli.wait_for_event` to raise `KeyboardInterrupt`; that patch is the only mock added.
- Test `test_sync_wait_ends_on_an_event_or_times_out_with_exit_2` (`tests/test_worker_cli.py`): A2 through the CLI. It covers an unacked event returning at once, a timeout with the empty delta and exit 2, and a thread appending during the wait ending it within 3 s with the usual output.
