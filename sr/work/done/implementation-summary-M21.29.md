# Implementation summary: M21.29 `terminate-ends-escaped-descendants`

Defect D6: `worker terminate` signalled only the wrapper's process group, so a command that the harness started in a session of its own (Cursor's shell tool) kept running after "terminated".

## What changed

- `specy_road/worker_process.py`: after `kill_group` verifies the group and before its first signal, it reads `ps -A -ww -o pid=,ppid=,pgid=,lstart=` once. It records every transitive descendant (by parent pid) of the group's members that is outside the group, with its start time. `lstart` is the rest of the line, stripped, which is how `start_token` reads it (A1). The group is then signalled as before; that loop moved unchanged into `_end_group`. Once the group is gone, each recorded descendant still listed with the same start time gets SIGTERM, then SIGKILL after the grace. A pid that is no longer listed, or whose start time changed, counts as gone and is never signalled. Each of these raises `WorkerError` after the group has been signalled, so `terminate` does not record `terminated` (A2):
  - a survivor, with its pid named
  - a failed, timed-out or unparsable inventory
  - a failed, timed-out or unparsable recheck
- `tests/test_worker_terminate_descendants.py` (new, POSIX only) (A3):
  - A fake harness whose child calls `os.setsid()`, writes a ready file (atomically) and sleeps. Terminate runs only once that file exists. Parametrized: through `worker terminate`, and with a child that ignores SIGTERM through `kill_group(grace=0.5)`. In both, the grandchild and the group are gone.
  - Three tests drive the public `kill_group` against a real session leader, with patched `subprocess.run` (the inventory command only) and `os.kill` (the fake pid only). They cover a changed start time (not signalled, no error), an unreadable inventory (`WorkerError`, the group still ended) and a same-start survivor (`WorkerError` naming the pid).
  - Every spawned pid is killed in `finally`.
- `docs/orchestration-workers.md`: the "Processes outside the group" paragraph is rewritten. It now says that terminate snapshots descendants before the first signal and ends those outside the group, and that it cannot see a process already re-parented before that snapshot (A4). It replaces the old "no `worker` command sees it" text.
- `CHANGELOG.md`: a `[Unreleased]` / Fixed entry (A4).

## Notes for reviewers

- Missing `ps`: the plan's "behave as today" is superseded by A2 and the plan-review decision. A failed descendant inventory now raises after the group is signalled. `_group_members`' own behaviour when `ps` is missing is unchanged.
- Liveness is judged from the `ps -A` table alone, as A2 specifies (listed with the same start time). A zombie descendant whose parent is outside the group and never reaps it would therefore be reported as a survivor. This is conservative: terminate fails rather than claiming success.
- The `docs/orchestration-workers.md` paragraph is written with long lines (like nearby paragraphs) so the file stays within the `sr/constraints/file-limits.yaml` 400-line docs cap (399 lines). Net docs line change: −1.
- Touch zones: no change needed. All edits are inside the four listed zones. `worker_ops_lifecycle.py` (`_terminate_locked`) calls `kill_group` unchanged.
- Red/green: with `specy_road/worker_process.py` at base, `pytest tests/test_worker_terminate_descendants.py` gives 4 failed and 1 passed. The changed-start test asserts that nothing is signalled, so it passes either way.

## Verification

- `pytest -n 4 tests/test_worker_terminate_descendants.py tests/test_worker_orphans.py tests/test_worker_cli.py tests/test_worker_faults.py tests/test_prerelease_workers.py`: 51 passed
- Full suite `pytest -n 4`: 5460 passed
- `ruff check specy_road tests scripts`: clean. `specy-road file-limits`: OK

## Added

- `_end_group` (worker_process.py): the existing group SIGTERM/SIGKILL/confirm loop moved out unchanged, so `kill_group` can run the descendant step after it.
- `_process_table`: one `ps -A -o pid=,ppid=,pgid=,lstart=` read, parsed strictly. Returns `None` on failure, timeout or an unparsable line (A1, A2).
- `_escaped_descendants`: the transitive descendants by ppid outside the group, with start times (A1).
- `_still_running`: the recheck by pid plus start time. Raises `WorkerError` when the table cannot be read (A2).
- `_end_escaped`: SIGTERM, grace, SIGKILL, then a final survivor check that raises naming the pids (A2).
- Guard in `kill_group`: raises `WorkerError` after the group is ended when the inventory failed (A2).
- `HARNESS` fake harness script (test): spawns the setsid grandchild with a ready-file handshake (A3).
- `test_terminate_ends_a_grandchild_in_its_own_session[default|ignore]`: the D6 regression, plus SIGKILL of a grandchild that ignores SIGTERM, with an explicit short grace (A3).
- `leader` fixture: a real session leader started through a parent that exits at once, so no zombie of the test stays in its group (A3 seam tests).
- `_seams` helper: patches `subprocess.run` (inventory command only) and `os.kill` (the fake pid only) to inject a fake escaped descendant (A3).
- `test_a_descendant_whose_start_time_changed_is_neither_signalled_nor_a_survivor` (A3).
- `test_an_unreadable_inventory_raises_after_the_group_is_signalled` (A3).
- `test_a_same_start_survivor_raises_naming_its_pid` (A3).
- `_gone` / `_kill` test helpers: poll for the absence of a pid (a zombie counts as gone), and clean up by recorded pid in `finally`.
