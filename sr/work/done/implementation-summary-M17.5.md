# Implementation summary: M17.5 — outline orchestration badges (`gui-orch-outline-badges`)

## What changed

- **`gui/pm-gantt/src/orchestrationSnapshot.ts`**: `outlineBadge` returns the one badge `leafBadge` already chooses, a hover, and the leaf `node_key` a click passes to `filterLeafId`. The hover is six lines: claim (codename, branch, registered age, or —), workers (`id status`, or —), worktree count, READY's short commit (or —), reviews (`model verdict`, or —), and holds. A hold-list entry with a reason is `hold list: <reason>`; one with a null reason is `hold list`; a gate hold is the open gate id. An empty or omitted holds list is —. A load that is not `ok` (404 `unavailable`, or any error), a leaf key the snapshot does not have, or a leaf `leafBadge` leaves blank all return null. `loadOrchestration` still does one GET and still never throws; after each result it notifies `subscribeOrchestration` listeners, including a 404. The outline uses that so it has no timer of its own.
- **`gui/pm-gantt/src/components/OutlineTable.tsx`**: a non-container row with a badge renders one button in the existing Task cell, labelled with the badge text, `title` set to the hover, class `worker-stall-badge`. The click calls `onOpenOrchestration` with that view-model `leafKey` and stops the row's click, long-press and double-click. A drag preview shows the badge and does not open the drawer. `TABLE_COLS` is still 6. A row with no badge adds nothing.
- **`gui/pm-gantt/src/App.tsx`** (+16 lines): subscribes for the life of the app, calls `fetchOrchestration()` once inside `loadSnapshot` (each roadmap refresh), passes the latest notice to the outline, and passes `filterLeafId`. The header Orchestration button opens the drawer with the filter cleared. A badge click sets the filter to that leaf key and opens the drawer. While the drawer is open, its existing loads (open, Refresh, and the 15 s poll) go through `loadOrchestration` and the outline takes each one.
- **`specy_road/pm_gantt_static/`**: rebuilt by `npm run build`.

## Touch zones (final)

Changed: `gui/pm-gantt/src/components/OutlineTable.tsx`, `gui/pm-gantt/src/orchestrationSnapshot.ts`, `gui/pm-gantt/src/orchestrationSnapshot.test.ts`, `gui/pm-gantt/src/App.tsx`, `specy_road/pm_gantt_static/`.

Zoned but unchanged: `gui/pm-gantt/src/App.css`. It is the unused Vite starter sheet, and `main.tsx` loads `index.css` only. Importing `App.css` would ship those starter rules. The badge reuses `worker-stall-badge` from `index.css` (the same class the drawer already uses for this badge) plus a small inline reset so the control is a button. `index.css` is outside the zones and did not need an edit.

No path outside the zones was needed. `OrchestrationDrawer.tsx` already calls `fetchOrchestration` → `loadOrchestration` and already accepts `filterLeafId`, so the outline hears the drawer's loads without a new prop on the drawer.

## Verification

- `cd gui/pm-gantt && npm ci && npm run lint && npm test && npm run build`: lint 0 errors, 42 warnings, all pre-existing (none on the new lines). Vitest: 30 files, 308 tests passed. Build wrote `specy_road/pm_gantt_static/`.
- No browser tools in this session. The badge text, hover and leaf key are pinned by the view-model rows; a click-through of the outline was not run.

## Accepted limits

- With the drawer closed, badges change when the outline reloads. They also change when any other caller of `loadOrchestration` finishes, including the edit modal's one-shot Orchestration section (M17.4). That is not a timer. The badge does not poll.
- There is no DOM test (planned limit). The button, `filterLeafId` and the 404 outline are for review, M17.8 and M17.9. Existing outline, `tableCols` and gantt tests were not edited.
- While a title is being edited, the Task cell shows the input in place of the title row, so the badge is hidden until the edit ends.
- Container rows (rows in `parentNodeIds`) do not show a badge. The view model is only asked for a leaf key on a row that is not a container.

## Added

- `OutlineBadgeView`: badge text, hover text, and the leaf key a click passes.
- `holdPhrase`: a hold-list reason is `hold list: <reason>`, a hold-list entry with a null reason is `hold list`, and any other hold (the open gate) is its id, or — when the id is missing.
- `badgeHover`: the six-line hover. A missing claim, an empty worker list, an empty review list, a missing READY and an empty or omitted holds list each read —.
- `outlineBadge`: one badge from `leafBadge`, or null. A non-ok load, a missing leaf and a leaf with no orchestration state are the three nulls.
- `OrchestrationNotice`: one load plus the `Date` the hover's ages are measured from.
- `subscribeOrchestration`: registers a listener for later `loadOrchestration` results and returns the unsubscribe function. The outline has no interval; it hears the roadmap refresh and each drawer load because both call `loadOrchestration`.
- Branch: `loadOrchestration` notifies listeners after a 200, a 404 and a thrown fetch, then returns the same result as before.
- Branch: the Task cell renders the button only when `outlineBadge` returns one. A container row, a row with no `node_key`, and a null notice skip it.
- Branch: the header Orchestration button clears `filterLeafId`; a badge click sets it to the view-model leaf key and opens the drawer.
- Branch: the drag-preview badge has no click handler.
- Guard: the badge button stops click, pointerdown and double-click so the row does not select, start a title edit or open the edit modal.
- Mocks: none.
- Test: `outlineBadge` on the mock's blocked leaf (badge `blocked (1)`, hover, leaf key `k-blocked`, holds —), the hold-list leaf (`hold list: waiting on the maintainer`), the gate hold (`holds: M9.3`), an `executor_blocked` leaf whose `gate.blocks` is 0 and whose READY has two `blocked_on` entries (`blocked (2)`), a hold list with a null reason beside a gate (`holds: hold list; G9`, the gate reason omitted), a claim with no workers (`holds: —`), a 404, an empty leaf, and a key the snapshot does not have.
- Test: `subscribeOrchestration` receives that load's kind for a 200 and a 404, and a load after unsubscribe does not append.
