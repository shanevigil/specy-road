# Implementation summary — M10.12 Visual explorer for worker event logs

Branch `feature/rm-visual-explorer-for-worker`, base `1d8d99e`. Commits: `272b347` (implementation), `54e0665` (packaged bundle rebuild), `e5b7a69` (`docs/orchestration-workers.md` pointer).

## What changed

- **A1 — routes.** New `specy_road/gui_app_routes_workers.py`, included from `specy_road/gui_app.py` (its own `APIRouter(prefix="/api")`, before the SPA fallback; `gui_app_api.py` is outside the touch zones, so the router is not assembled there).
  - `GET /api/workers`: one row per worker (`worker_id`, `node_id`, `harness`, `model`, `state`, `attempt`, `flags`, `updated`, `last_event`, `total_cost_usd`, `cost_is_estimate`).
  - `GET /api/workers/{id}/events`: that row plus `events` (the log), `phases` (seconds per phase of the latest turn) and `usage` (totals); 404 for an unknown or malformed id (`record_path`'s `w-NNNN` check).
  - Reads only: `list_records`, `load_record`, `events_since`, `sync_marks`. No `sweep_stalled`, no ack, no lock. `workers_dir` resolves the **main** worktree's `work/.workers/`, the same as the CLI.
  - Phase and cost arithmetic reuse `timeline()` and `usage()` from `specy_road/bundled_scripts/worker_cli_render.py`; nothing is re-derived. The brief names `specy_road/worker_cli_render.py`, but the file is under `bundled_scripts/`.
- **A2 — drawer.** `gui/pm-gantt/src/components/WorkersDrawer.tsx`, modelled on `WorkNotesDrawer.tsx`, opens from a new **Workers** header button in `App.tsx` (lazy-loaded like the other drawers).
  - Sidebar: workers grouped by leaf. Each row shows attempt, id, state, harness/model and cost per attempt (`$?` when no cost was reported).
  - Detail: a phase bar built from `phases`, the usage totals, and the event list. Tool-call lines are labelled `tool`. `stalled` events get a marker, and a `stalled ×N` badge appears when any exist.
  - The math is in `gui/pm-gantt/src/workerTimeline.ts`. Styles are appended to `src/index.css`. Client functions are `fetchWorkers` and `fetchWorkerEvents` in `api.ts`; the types are in `types.ts`.
- **A3.** No new npm dependency (`package.json` and the lockfile are untouched). From `gui/pm-gantt`, `npm ci`, `npm run lint`, `npm test` and `npm run build` all pass. Lint has 0 errors, and none of the existing warnings are in the new files.
- **A4.** `docs/pm-gui.md` has a **Workers drawer** entry. `tests/test_gui_app_workers.py` covers both routes. `src/workerTimeline.test.ts` (vitest) covers the phase-bar math.

## Touch zones (final list)

Used: `specy_road/gui_app.py`, `specy_road/gui_app_routes_workers.py`, `gui/pm-gantt/src/`, `docs/pm-gui.md`, `tests/test_gui_app_workers.py`, `specy_road/pm_gantt_static/` and `docs/orchestration-workers.md` (the last two added to the touch zones on WIP in `538be8a`, merged here in `fc8669d`).

Listed but not needed: `specy_road/gui_app_routes_workspace.py` and `tests/test_gui_app.py`.

## Follow-up round (touch zones widened)

- **Packaged bundle.** `npm ci && npm run lint && npm test && npm run build` re-run in the foreground from `gui/pm-gantt` (lint 0 errors; 23 files / 181 tests passed; built). The rebuilt `specy_road/pm_gantt_static/` is committed on its own as `54e0665 build(gui): …`, so `specy-road gui` now serves the drawer. Its entry chunk `index-2teI54Ey.js` is 94,018 bytes, well under CI's 900 KB budget.
- **`docs/orchestration-workers.md`.** The file was at 398 of its 400-line cap, so the pointer to the Workers drawer is one sentence added to the end of the `usage W|NODE_ID` command row. It adds no lines; the file is still 398 lines.

## Verification

- `pytest tests/test_gui_app.py tests/test_gui_app_workers.py`: 22 passed (re-run after the WIP merge).
- `specy-road file-limits`: OK (re-run after the doc pointer).
- Full `pytest`, run in chunks because one run exceeds this harness's 10-minute foreground limit: every test passed (2 skipped). When four chunks ran at once, `tests/test_worker_faults.py::test_output_clears_a_stall_shorter_than_the_write_window` hit its log-line deadline. Run alone, `tests/test_worker_faults.py` gives 7 passed. That is load-dependent timing in a file this leaf does not touch.
- `scripts/check_test_private_imports.py`: 0 new. `ruff check` on the new and changed Python: clean.
- `scripts/check_clones.py` could not run here: `pylint` is not installed.

## Added

### Python
- `specy_road/gui_app_routes_workers.py::_last_event` — the row's last event, trimmed to seq/at/type/source/summary for the list.
- `specy_road/gui_app_routes_workers.py::_row` — one list row; the total cost comes from `worker_cli_render.usage()`, so a cost nobody reported stays `None`.
- `specy_road/gui_app_routes_workers.py::_api_workers` — `GET /api/workers`.
- `specy_road/gui_app_routes_workers.py::_api_worker_events` — `GET /api/workers/{id}/events`.
- Guard in `_api_worker_events`: `WorkerError` → 404, so an unknown or malformed id is not a 500.
- `specy_road/gui_app_routes_workers.py::register_worker_routes` — attaches the routes; called from `gui_app.create_app`.
- `specy_road/gui_app.py` — an `APIRouter(prefix="/api")` for the worker routes, included before the SPA catch-all.

### Frontend
- `gui/pm-gantt/src/workerTimeline.ts::phaseLabel` — phase key → readable label.
- `gui/pm-gantt/src/workerTimeline.ts::phaseSegments` — segment widths as a share of the known phases; unknown or zero phases get no width (A2 phase bar).
- `gui/pm-gantt/src/workerTimeline.ts::formatSeconds` — `42s` / `3m 05s` / `1h 02m` / `unknown`.
- `gui/pm-gantt/src/workerTimeline.ts::formatCost` — `$?` for an unreported cost, distinct from `$0.0000`.
- `gui/pm-gantt/src/workerTimeline.ts::isToolCall` — recognises the adapters' tool-call `output` summaries (Claude, Cursor, Codex) for the A2 "tool-call lines".
- `gui/pm-gantt/src/components/WorkersDrawer.tsx::groupByNode` — workers per leaf (A2).
- `gui/pm-gantt/src/components/WorkersDrawer.tsx::PhaseBar` — the bar and its legend.
- `gui/pm-gantt/src/components/WorkersDrawer.tsx::WorkerDetailView` — detail pane: header, stall badge, usage line, event list with tool and stall markers.
- `gui/pm-gantt/src/components/WorkersDrawer.tsx::WorkersDrawer` — the drawer; it loads on open and keeps the selection on Refresh.
- `gui/pm-gantt/src/api.ts::fetchWorkers`, `fetchWorkerEvents` — the two GET calls.
- `gui/pm-gantt/src/types.ts::WorkerRow`, `WorkerEvent`, `WorkerDetail` — response types.
- `gui/pm-gantt/src/App.tsx` — `workersOpen` state, the lazy `WorkersDrawer`, and the header **Workers** button.
- `gui/pm-gantt/src/index.css` — `.worker-*` styles, using only existing theme tokens so dark mode follows.
- `specy_road/pm_gantt_static/` — the rebuilt bundle, including the new lazy `WorkersDrawer-*.js` chunk; it is generated output, not hand-written.
- `docs/orchestration-workers.md` — one sentence on the `usage` row pointing at the drawer.

### Tests
- `tests/test_gui_app_workers.py::repo` (fixture) — a review repo with one failed worker (launch, tool line, stall, two usage events, turn end) and a second attempt that has reported nothing; `SPECY_ROAD_REPO_ROOT` points at it.
- `test_list_has_one_row_per_worker_with_cost_and_last_event` — A1 list fields; cost summed; an unreported cost is `None`, not 0.
- `test_events_route_returns_log_phases_and_usage_totals` — A1 event route: log order, phase keys and values, unacked end is `None`, usage totals.
- `test_unknown_or_malformed_worker_id_is_404` — the 404 guard.
- `test_routes_never_write_the_workers_directory` — A1 "never written": byte snapshot of `work/.workers/` before and after.
- `test_no_workers_directory_lists_nothing` — an empty list, and no directory is created.
- `gui/pm-gantt/src/workerTimeline.test.ts` — A4 vitest: segment percentages and order, all-unknown, `formatSeconds`, `formatCost` keeping `?` apart from 0, `isToolCall` per harness.

### Mocks
- none
