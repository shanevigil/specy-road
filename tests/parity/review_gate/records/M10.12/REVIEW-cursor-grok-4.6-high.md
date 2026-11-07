---
node_id: M10.12
model: cursor-grok-4.6-high
date: '2026-11-02'
verdict: approve
commit: 6a60d4bca08c960584f637150c959920633e16ec
acceptance:
  A1: pass
  A2: pass
  A3: pass
  A4: pass
findings:
  correctness: []
  regression: []
  boundary: []
  test_integrity: []
commands_rerun:
- python -m pytest tests/test_gui_app.py tests/test_gui_app_workers.py -q --tb=short
- specy-road file-limits
- npm run lint && npm test && npm run build (from gui/pm-gantt)
required_changes: []
fresh_session: true
authored_fix: false
is_coordinator: false
notes_sha256: 7c896e36af93172ada5f2b2ec88fa3bd39d079d7239dcea9fa224e4ab22bc953
family: xai
---

Reviewed `6a60d4bca08c960584f637150c959920633e16ec` (`feature/rm-visual-explorer-for-worker`) from the packet against base `538be8aa9416245a273b7ad8c4c3a220a9e1597e`. Precondition: `PACKET.md` exists; porcelain excluding this leaf's brief/summary/prompts/reviews was empty. HEAD matches the commit under review. No tracked file edited; no `specy-road session` started.

## Acceptance

- **A1 pass.** `GET /api/workers` and `GET /api/workers/{id}/events` are registered from `specy_road/gui_app_routes_workers.py` on an `/api` router included in `create_app` before the SPA catch-all. List rows include id, node, harness, model, state, last event and total cost. The events route adds the log, `timeline()` phases and `usage()` totals (CLI arithmetic, not re-derived). Call chain is `get_repo_root` → `project_root`, then `list_records` / `load_record` / `events_since` / `sync_marks`. `workers_dir` is `reviews_root(...).parent / ".workers"`, so a linked worktree still reads the main worktree. No `sweep_stalled`, ack, lock, or mkdir. Unknown/malformed id is 404 via `WorkerError` from `record_path` / `load_record`. Snapshot test leaves `work/.workers/` bytes unchanged; a missing directory lists `[]` and is not created.

- **A2 pass.** Source: lazy `WorkersDrawer`, header **Workers** button, workers grouped by leaf, phase bar from `phaseSegments`, usage line, tool-call labels (`isToolCall`), stall markers and `stalled ×N`. Packaged GUI at this commit: `specy_road/pm_gantt_static/index.html` loads `index-Bqjz7U4A.js` (94,031 bytes), which maps `WorkersDrawer-ChfMVQaq.js`; that chunk contains `workers-drawer-title`. Round-1 P2: `createWorkerSelection` uses a request token plus `AbortController`; details clear on a new select; superseded replies/errors are dropped.

- **A3 pass.** `gui/pm-gantt/package.json` and the lockfile are not in the diff. Re-ran lint (0 errors, 52 pre-existing warnings, none in the new files), vitest (24 files / 184 tests), and `npm run build` (exit 0). Rebuild hashes matched HEAD (`git status` clean afterward). Did not re-run `npm ci`; no lockfile change.

- **A4 pass.** `docs/pm-gui.md` documents the Workers drawer. `docs/orchestration-workers.md` points at it from the `usage` row. `tests/test_gui_app_workers.py` covers both routes (list fields, events/phases/usage, 404, never-write, empty dir). `workerTimeline.test.ts` covers phase-bar math.

## Findings

- correctness: none
- regression: none. Re-ran `tests/test_gui_app.py` with the new routes mounted; 22 passed. Frontend suite 184 passed.
- boundary: none. Changed paths stay inside the listed touch zones, plus the required `sr/work/implementation-summary-M10.12.md`. Listed but unused: `specy_road/gui_app_routes_workspace.py`, `tests/test_gui_app.py` (the latter was still re-run).
- test_integrity: none. Packet reports no weakened or deleted tests. New Python tests hit the public HTTP API and do not import production `_`-prefixed names.

## Excess

Summary has a `## Added` inventory; it matches the diff (routes, drawer, timeline/selection helpers, types, tests, packaged bundle, docs).

- *Test pins internals:* not proven. `tests/test_gui_app_workers.py` uses `TestClient` on `/api/workers`. `workerTimeline.test.ts` imports exported helpers. `workerSelection.test.ts` drives public `createWorkerSelection` and asserts resulting state; `signal.aborted` is the `AbortSignal` passed into `fetchDetail`, not a mock call count.
- *Unreachable defence:* not proven. `WorkerError` → 404 is reached by `GET /api/workers/w-9999/events` and `GET /api/workers/sync/events`. `_last_event`'s empty-list branch is reachable when `events_since` finds no jsonl for a listed yaml (it returns `[]` if the file is missing).
- *Duplicated logic:* not proven. Phase seconds come from existing `worker_cli_render.timeline`; `phaseSegments` maps those seconds to bar percentages (different inputs/outputs). GUI `formatCost` is a TS display helper, not a second owner of the CLI `usage()` totals.
- *Overlapping test:* not proven. Each Python test is a distinct input class. `workerSelection.test.ts` is the out-of-order selection regression from review round 1; `workerTimeline.test.ts` is the A4 phase-bar math.

No required change from this checklist.