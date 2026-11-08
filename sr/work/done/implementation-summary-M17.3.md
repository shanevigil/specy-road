# Implementation summary: M17.3 — Orchestration drawer (`gui-orch-drawer`)

## What changed

- **`gui/pm-gantt/src/components/OrchestrationDrawer.tsx`** (new, lazy): a read-only `ModalFrame` drawer over M17.2's `buildOrchestrationView`. One group per leaf in view-model order, then "No leaf". A leaf header shows the display id (a link to the existing edit modal when the leaf key is in the loaded outline, plain `<code>` otherwise), title, leaf badge, a "Copy handoff status" button and a claim line (codename, branch, registered age). Worker rows show id (opens the Workers drawer on that worker), harness / model, account (a null account is an empty cell), status (so `exited_failed` shows there), last activity, started, ended, one badge per `flags` entry verbatim, and two copy buttons (`worker status`, `worker open`). Props: `open`, `onClose`, `nodes`, `onOpenNode`, `onOpenWorker`, optional `filterLeafId` (a leaf `node_key`; null or absent shows every group, the "No leaf" group included). A 404 shows "This server does not provide the orchestration snapshot yet."; any other failure shows its message. Ages are computed against the time of the last load. The only import from `api.ts` is `fetchOrchestration`. With `import.meta.env.DEV` and `?mock=orchestration`, it loads the M17.2 mock through a dynamic import; the production build drops that branch (no mock chunk, no `mock` string in `specy_road/pm_gantt_static/`).
- **`gui/pm-gantt/src/orchestrationSnapshot.ts`**: `loadOrchestration(fetchImpl)` (one GET of `/api/orchestration`, never throws: `ok` / `unavailable` on 404 / `error`), `pollOrchestration(load)` (loads now and every 15 s, returns the stop function the drawer's effect uses as cleanup, so the interval is cleared on close and unmount and nothing is requested while closed), and `copyCommand(kind, id)` (`specy-road <kind> <id>`, single-quoting for a POSIX shell any id outside `[A-Za-z0-9._-]+`).
- **`gui/pm-gantt/src/api.ts`**: `fetchOrchestration()` = `loadOrchestration(fetch)`. No existing request changed.
- **`gui/pm-gantt/src/workerSelection.ts`**: `pickWorkerId(ids, preferId)` — the listed `preferId`, else the newest (last listed). This is the rule `WorkersDrawer.load` already applied inline, moved out so it is tested.
- **`gui/pm-gantt/src/components/WorkersDrawer.tsx`**: optional `initialWorkerId` prop, selected through `createWorkerSelection` on open via `pickWorkerId`; without it the newest-worker default stays. Refresh keeps the current selection exactly as before.
- **`gui/pm-gantt/src/App.tsx`** (+29 / −1, net +28): the lazy `OrchestrationDrawer`, `orchestrationOpen` plus `workersInitialId` state, the "Orchestration" header button next to "Workers", and the mount. The mount sits before `WorkersDrawer`, so a worker link opens the Workers drawer in front of it. Closing the Workers drawer clears `workersInitialId`, so the header "Workers" button keeps opening on the newest worker.
- **`specy_road/pm_gantt_static/`**: rebuilt by `npm run build`.

## Touch zones (final)

Changed: `OrchestrationDrawer.tsx`, `orchestrationSnapshot.ts`, `orchestrationSnapshot.test.ts`, `api.ts`, `App.tsx`, `WorkersDrawer.tsx`, `workerSelection.ts`, `workerSelection.test.ts`, `specy_road/pm_gantt_static/`.
Zoned but unchanged: `App.css` (it is the unused Vite template stylesheet, not imported anywhere; the drawer reuses existing `index.css` classes: `workspace-file-table`, `worker-section-title`, `worker-stall-badge`, `modal-dep-id-link`, `outline-meta`, `workspace-empty`, `workspace-notes-actions`) and `fixtures/orchestration_snapshot_mock.json`. No path outside the zones was needed.

## Verification

- `cd gui/pm-gantt && npm ci && npm run lint && npm test && npm run build`: lint 0 errors (warnings unchanged; none in the changed files; `App.tsx` 9 before and after), 30 files / 304 tests pass, build succeeds.
- `specy-road file-limits`: OK.
- `pytest -n 4 tests/test_verify_wheel_contents.py tests/test_update_specy_road.py` (static-bundle tests): 19 passed.

## Accepted limits

- There is still no DOM test (planned limit): the component's use of `pollOrchestration`, `copyCommand`, the 404 text, `filterLeafId` and the links is checked by review, M17.8's live check and M17.9's browser run. The "no request while closed" half of A3 rests on the effect's `if (!open) return`; the vitest row covers stop-on-close.
- `filterLeafId` matches the snapshot's leaf key (`node_key`), not the display id, since that is the snapshot's identity; M17.5 should pass a `node_key`.
- A Refresh click and a poll tick can overlap; the later reply wins. Both read the same snapshot seconds apart, so no request token was added.

## Added

- `loadOrchestration` (orchestrationSnapshot.ts): A2's injected-fetch loader; GET, 404 → unavailable, else error.
- `try`/`catch` in `loadOrchestration`: a rejected fetch (network down, server stopped) or a non-JSON body becomes `error` instead of an unhandled rejection; reached by the "a network failure" and "a body that is not JSON" rows.
- `pollOrchestration` (orchestrationSnapshot.ts): A3's one 15 s interval, owned outside React so fake timers test it.
- `copyCommand` and `CopyKind` (orchestrationSnapshot.ts): A4's pure command builder with POSIX single-quoting.
- `OrchestrationLoad` type: the loader's three outcomes the drawer renders.
- `fetchOrchestration` (api.ts): A2's API entry point.
- `pickWorkerId` (workerSelection.ts): A3's `initialWorkerId` pick; it replaces WorkersDrawer's inline keep-or-newest lookup.
- `initialWorkerId` prop on WorkersDrawer: A3's link into the Workers drawer.
- `OrchestrationDrawer`, `CopyButton`, `GroupView` (OrchestrationDrawer.tsx): A1's drawer; `load()` there holds A2's dev-only mock switch.
- Branch: leaf id is a link only when its key is in the loaded outline; a snapshot key missing from the outline (the mock's `k-exec-blocked`) would otherwise push an id with no node into the edit-modal stack.
- Branch: "No workers." when a leaf has a claim but no workers, instead of an empty table.
- `try`/`catch` in the drawer's copy handler: A4's "copy failed" when `navigator.clipboard` is missing (non-secure context) or the write is refused.
- App.tsx state `workersInitialId` and the reset in WorkersDrawer's `onClose`: carry the worker link; the reset keeps the header "Workers" button on the newest worker.
- Mocks: `recordingFetch` and `respond` (orchestrationSnapshot.test.ts), an injected fetch that records `METHOD url` per request; vitest fake timers for the poll.
- Tests, orchestrationSnapshot.test.ts: `loadOrchestration` (200 → one GET and the snapshot; 404 → unavailable; three error rows: 500, network failure, non-JSON body); `pollOrchestration` (open → 1, +15 s → 2, stopped → none for 60 s); `copyCommand` (five rows, one with a quote, a space and `$(...)`, one with `;`); the OrchestrationDrawer.tsx source-import check, plus four rows showing the `apiImports` extractor catches an extra named import, a namespace import, a multi-line type import and a dynamic import.
- Tests, workerSelection.test.ts: `pickWorkerId` through `createWorkerSelection` (initialWorkerId listed → selected; none → newest; unlisted → newest) and an empty list → null.
