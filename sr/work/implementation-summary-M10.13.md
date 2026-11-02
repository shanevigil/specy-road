# Implementation summary: M10.13 — A project setting decides whether agent logs are tracked in git

Branch `feature/rm-a-project-setting-decides`; code commits `c10a687` (feature) and `7610ee7` (review round 1: gpt-6.1-sol R1, R2).

## What changed

- **A1.** `roadmap/git-workflow.yaml` accepts `track_worker_logs: "off" | "events" | "full"` (schema `enum`, plus YAML `false`, because a bare `off` loads as `false`). Any other value fails the schema, so `load_git_workflow_config` (and `specy-road validate`, which calls it) reports `track_worker_logs: ... is not one of ...`. `git_workflow_config.track_worker_logs()` returns the mode, or `"off"` when the key is absent, false, or the config is unreadable. The template schema and `sr/schemas/` were refreshed with `refresh-schemas`. The template `git-workflow.yaml` has a commented, quoted `track_worker_logs: "off"`.
- **A2.** `worker_runner.mirror_logs()` copies the event log byte for byte to `work/worker-logs/<NODE_ID>/<worker id>.events.jsonl` (and `<worker id>.log` under `full`) in the **worker's own checkout** (`rec.worktree` + the project prefix). It copies only the tail the mirror lacks, so events appended between turns (`message` and similar) are picked up next time. It runs when a turn ends, not per line: in `_exit_state` (after the turn's last event, before the record clears its pid, so a waiter sees the complete copy), and on the can't-start path before the `failed` state. A copy in the worktree during the turn would be an untracked change under the executor's clean-tree precondition, which agents run before their first edit. Under `off` it returns before touching the filesystem. `finish_work_artifacts.worker_logs_to_stage()` returns `work/worker-logs/<NODE_ID>` when the mode is on and the directory has files. `finish_task.py` adds it to the bookkeeping commit's `git add` independently of `--no-cleanup-work` / `cleanup_work_artifacts_on_finish`. Nothing deletes it. If a consumer `.gitignore` covers the directory, finish warns and skips it rather than letting `git add` fail the finish.
- **A3.** `agent_ignores.py` is unchanged: `work/.workers/` and `work/.worktrees/` stay in the managed block, and nothing matches `work/worker-logs/`. A new test checks this through `git check-ignore`, in the embedded and nested layouts.
- **A4.** `docs/git-workflow.md` documents the key, its default, the quoting, the size warning and the `.gitignore` caveat. `docs/orchestration-workers.md` covers where logs live per mode; it is at its 400-line cap, so I edited existing lines and added none. The work README does the same.

- **Review round 1 (gpt-6.1-sol block).**
  - **R1:** the wrapper mirrors after the executor has committed and written READY, so the mirror used to make the reviewer's (and a later executor's) clean-tree check stop. `role_prompt_rca.dirty_check(prefix, node_id)` (the executor and other roles) and `reviewer_precondition` now leave out `<prefix>work/worker-logs/<NODE_ID>/`: that leaf's directory only, so another leaf's logs and any other change still count. The prompt prose names the exclusion.
  - **R2:** `worker_reconcile._bookkeeping` recognises the same directory (this leaf's only). So `reconcile` no longer reports the mirror outside the touch zones, and `worker_ops._launch_locked` (unchanged; it calls `_bookkeeping`) no longer refuses it as uncommitted work on re-delegation. `docs/orchestration-workers.md` adds the directory to delegate's bookkeeping list, editing a line in place at its 400-line cap.

## Verification

- `pytest tests/test_worker_state.py tests/test_finish_work_cleanup.py tests/test_agent_ignores.py -q` → 50 passed (after round 1).
- Both round-1 regression tests fail against the pre-fix `role_prompt_rca.py` / `worker_reconcile.py` (checked by restoring the committed versions temporarily): the reviewer check printed `?? work/worker-logs/M1.1/w-0001.events.jsonl`, and reconcile listed it in `outside_touch_zones`.
- `specy-road file-limits` → OK. `specy-road validate --repo-root sr` → OK. Both were run through this worktree's package (`python -c "from specy_road.cli import main; ..."`), since the `specy-road` on PATH runs the main checkout.

## Touch zones (final)

The listed zones, plus the three added after the first stop (`specy_road/templates/project/schemas/git-workflow.schema.json`, `sr/schemas/git-workflow.schema.json`, `specy_road/bundled_scripts/finish_task.py`) and the three added for review round 1 (`specy_road/bundled_scripts/role_prompt_rca.py`, `specy_road/worker_reconcile.py`, `specy_road/worker_ops.py`). These were unchanged: `worker_state.py` (at its cap; the mirror lives in `worker_runner.py`), `agent_ignores.py` (A3 already held) and `worker_ops.py` (at its cap; covered through `_bookkeeping`).

## Notes

- The two gaps listed here before round 1 (reconcile/re-delegation and the clean-tree preconditions) are fixed; see R1 and R2 above.
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
- Round 1: `role_prompt_rca.dirty_check()` takes an optional `node_id` and appends `':(top,exclude)<prefix>work/worker-logs/<NODE_ID>/'` (R1: executor and other roles' precondition). `precondition()` passes the node id.
- Round 1: an extra exclude pathspec in `reviewer_precondition()`, plus a prose mention (R1: the reviewer's precondition).
- Round 1: `worker_reconcile._bookkeeping()` gains the `work/worker-logs/<NODE_ID>/` prefix, this leaf's only (R2: reconcile zones and re-delegation).
- Round 1: `mirror_logs` moved into `worker_runner._exit_state()` and ahead of `set_state("failed")` on the can't-start path, from after `_finish`. Waiting on `pid is None` then sees a complete mirror; the delegate-driven R2 test depends on that.
- Round 1 test: `tests/test_finish_work_cleanup.py::test_an_opted_in_completed_worker_goes_through_review_to_finish`. A real wrapper turn writes READY and the worker ends `completed` with the mirror present. The reviewer prompt's and the executor precondition's commands print nothing, while another leaf's log still shows. Then `mark-implementation-reviewed --yes` → 0 and `finish-this-task` → 0, with the mirror in the `complete, deregister` commit. Helpers `READY_WRITER`, `_status`.
- Round 1 test: `tests/test_worker_state.py::test_a_leafs_own_worker_logs_neither_breach_zones_nor_block_redelegation`. Through `ops.delegate` / `reconcile` / `terminate`: the leaf's own mirror is in `changed` but not in `outside_touch_zones`; another leaf's log is outside the zones and blocks `delegate`; with it removed, re-delegation succeeds.
- Mocks: none. The mirror tests run the real wrapper on a `python -c` / script harness.
