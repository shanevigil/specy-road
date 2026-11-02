# Implementation summary: M10.13 — A project setting decides whether agent logs are tracked in git

Branch `feature/rm-a-project-setting-decides`; code commit `c10a687`.

## What changed

- **A1.** `roadmap/git-workflow.yaml` accepts `track_worker_logs: "off" | "events" | "full"` (schema `enum`, plus YAML `false`, because a bare `off` loads as `false`). Any other value fails the schema, so `load_git_workflow_config` (and `specy-road validate`, which calls it) reports `track_worker_logs: ... is not one of ...`. `git_workflow_config.track_worker_logs()` returns the mode, or `"off"` when the key is absent, false, or the config is unreadable. The template schema and `sr/schemas/` were refreshed with `refresh-schemas`. The template `git-workflow.yaml` has a commented, quoted `track_worker_logs: "off"`.
- **A2.** `worker_runner.mirror_logs()` copies the event log byte for byte to `work/worker-logs/<NODE_ID>/<worker id>.events.jsonl` (and `<worker id>.log` under `full`) in the **worker's own checkout** (`rec.worktree` + the project prefix). It copies only the tail the mirror lacks, so events appended between turns (`message` and similar) are picked up next time. It runs when a turn ends (after `_finish`, and on the can't-start path), not per line. A copy in the worktree during the turn would be an untracked change under the executor's clean-tree precondition, which agents run before their first edit. Under `off` it returns before touching the filesystem. `finish_work_artifacts.worker_logs_to_stage()` returns `work/worker-logs/<NODE_ID>` when the mode is on and the directory has files. `finish_task.py` adds it to the bookkeeping commit's `git add` independently of `--no-cleanup-work` / `cleanup_work_artifacts_on_finish`. Nothing deletes it. If a consumer `.gitignore` covers the directory, finish warns and skips it rather than letting `git add` fail the finish.
- **A3.** `agent_ignores.py` is unchanged: `work/.workers/` and `work/.worktrees/` stay in the managed block, and nothing matches `work/worker-logs/`. A new test checks this through `git check-ignore`, in the embedded and nested layouts.
- **A4.** `docs/git-workflow.md` documents the key, its default, the quoting, the size warning and the `.gitignore` caveat. `docs/orchestration-workers.md` covers where logs live per mode; it is at its 400-line cap, so I edited existing lines and added none. The work README does the same.

## Verification

- `pytest tests/test_worker_state.py tests/test_finish_work_cleanup.py tests/test_agent_ignores.py -q` → 48 passed.
- `specy-road file-limits` → OK. `specy-road validate --repo-root sr` → OK. Both were run through this worktree's package (`python -c "from specy_road.cli import main; ..."`), since the `specy-road` on PATH runs the main checkout.

## Touch zones (final)

The listed zones, plus the three added after the first stop: `specy_road/templates/project/schemas/git-workflow.schema.json`, `sr/schemas/git-workflow.schema.json`, `specy_road/bundled_scripts/finish_task.py`. These were unchanged: `worker_state.py` (at its cap; the mirror lives in `worker_runner.py`) and `agent_ignores.py` (A3 already held).

## Known gaps (outside the zones, not changed)

With tracking on, the untracked mirror in the worker's checkout is not recognised as the leaf's bookkeeping by:
- `worker_reconcile._bookkeeping` (`_STATE_DIRS`), so `reconcile` counts it as a change and a re-`delegate` of the same leaf into that worktree refuses it as uncommitted. Adding `f"work/worker-logs/{node_id}/"` there would fix both.
- the executor/reviewer clean-tree precondition built in `bundled_scripts/role_prompt_rca.py`. The first turn is safe, because mirroring happens at turn end; a later fresh executor prompt in the same worktree would see the mirror unless that pathspec excludes `work/worker-logs/<NODE_ID>/`.
- `sr/schemas/orchestration.schema.json` had pre-existing drift that `refresh-schemas` also rewrote; I restored it, as it is not this leaf's.

## Added

- `git_workflow_config.TRACK_WORKER_LOGS_MODES`, `WORKER_LOGS_REL`, `track_worker_logs()`: the one accessor (and shared path) for the setting, which falls back to `off`.
- Schema property `track_worker_logs` (`enum: off, events, full, false`): A1, where `false` covers bare YAML `off`.
- `worker_runner.mirror_dir()`: the mirror location in the worker's own checkout.
- `worker_runner.mirror_logs()`: copies per mode at turn end. Its `OSError` guard writes a `[wrapper]` note to the raw log, so the audit copy never fails the turn.
- `worker_runner._copy_tail()`: an incremental byte-exact append, which avoids recopying a growing log every turn.
- Two `mirror_logs` call sites in `run()`: after `_finish`, and on the harness-could-not-start path.
- `finish_work_artifacts.worker_logs_to_stage()`, with its `git check-ignore` guard: finish staging independent of cleanup. The guard turns a consumer-ignored directory into a warning, not a failed `git add`.
- `finish_task.py`: one `changed_files.extend(worker_logs_to_stage(...))` line and its import.
- Tests in `tests/test_worker_state.py`: `test_track_worker_logs_accepts_off_events_and_full` (absent, bare off, "off", "events", full), `test_track_worker_logs_rejects_any_other_value` (on, Full, "raw", 1), `test_events_mode_mirrors_the_event_log_into_the_workers_checkout` (linked worktree, events then full, catch-up between turns, stderr in the raw mirror), `test_off_writes_nothing_outside_work_workers`. Helpers `_track`, `_turn`, `_worker_in_linked_tree`.
- Tests in `tests/test_finish_work_cleanup.py`: `test_worker_logs_are_staged_when_tracked_and_survive_cleanup` (`git add` stages exactly the log), `test_worker_logs_are_not_staged_when_off_or_absent`, `test_worker_logs_a_consumer_ignores_are_skipped_with_a_warning`. Helper `_logs_repo`.
- Test in `tests/test_agent_ignores.py`: `test_worker_state_stays_ignored_and_worker_logs_never_are` (A3, both layouts).
- Mocks: none. The mirror tests run the real wrapper on a `python -c` harness.
