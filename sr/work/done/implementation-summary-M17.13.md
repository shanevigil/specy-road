# Implementation summary: M17.13 `gui-outline-selection-lag`

## What changed

- `gui/pm-gantt/src/outlineRowClick.ts` (new, pure): `createOutlineRowClick()` holds the click / double-click decision. A click selects at once and arms a 220 ms window (`DOUBLE_CLICK_MS`, the old delay). A second click on the same row inside that window opens the edit modal and does not select again. When the window ends, the next click is another select. A click while a title is being edited selects nothing and opens nothing. `toolbarTarget()` is the id selected by the last selecting click, with no wait. `rowDragAttributes` copies `useSortable`'s attributes and drops `aria-disabled` when drag alone is disabled.
- `gui/pm-gantt/src/components/OutlineTable.tsx`: the delayed select was `handleTitleClick` (there is no `handleRowClick`; the coordinator resolution names `handleTitleClick`). It now asks the shared helper and calls `onSelectRow` on that click. The helper lives on the table, so the first click's selection re-render does not clear the window, and the second click still opens the modal. The row's double-click handler still opens the modal. Long press, the id cell, and dependency-edit clicks keep their current behaviour (a dependency click disarms the window so it cannot open the modal). The attributes spread onto the row are `rowDragAttributes(attributes, dragDisabled)`.
- `gui/pm-gantt/src/App.tsx`: `selectRow` writes `selectedIdRef` and React state together. Add above, Add below, Indent, Outdent, Delete, and the other selection toolbar actions (edit, group siblings, insert gate) read `selectedIdRef` in the click handler. There is no Move toolbar button. Indent and outdent are the toolbar moves; dragging a row uses the dragged row's id, not this selection.
- `specy_road/pm_gantt_static/`: rebuilt with `npm run build`.
- `CHANGELOG.md`: an `[Unreleased]` / Fixed entry.

## Decisions

- **Which handler:** `handleTitleClick` waited 220 ms before `onSelectRow`. Id and status clicks already selected immediately. The acceptance text says `handleRowClick`; that function does not exist.
- **Double click after the re-render:** the window is on the table's helper, not in row state. The second title click opens the modal even when the first click has already selected the row. The row's `onDoubleClick` still opens it too; `openEditNode` is idempotent for a row that is already open.
- **Toolbar:** the handlers read the ref written on the selecting click, so they do not use the selection from the render that painted the button. A layout effect copies `selectedId` back onto the ref when the snapshot load or Hide complete changes the selection without a click.
- **Drag and aria-disabled:** `useSortable({ disabled: dragDisabled })` still disables drag. The row does not receive `aria-disabled` from those attributes.

## Touch zones

Changed: `gui/pm-gantt/src/components/OutlineTable.tsx`, `gui/pm-gantt/src/outlineRowClick.ts`, `gui/pm-gantt/src/outlineRowClick.test.ts`, `gui/pm-gantt/src/App.tsx`, `specy_road/pm_gantt_static/`, `CHANGELOG.md`.

Unchanged: `gui/pm-gantt/src/usePmGuiHandlers.ts`. It only exposes `onConcurrencyConflict`. The selection the toolbar reads lives in `App.tsx`.

No change was needed outside the zones. File limits do not apply to these TypeScript files (their globs are Python and docs).

## Verification

- `cd gui/pm-gantt && npm ci && npm run lint && npm test && npm run build`: pass. Lint: 0 errors, 42 warnings, none in the new files. The 8 warnings in `App.tsx` are on lines that were already there. Vitest: 30 files, 284 tests. Build wrote `specy_road/pm_gantt_static/`.
- Not checked in a browser: this session had no browser automation. The click, double-click, title-edit, toolbar-target and aria-disabled cases are the vitest rows over `outlineRowClick.ts`.

A4 (informational): frontend source about +99 (`outlineRowClick.ts` 74, `App.tsx` +21, `OutlineTable.tsx` +4) and +65 vitest lines, plus 5 CHANGELOG lines. The estimate was about +60.

## Added

- Module `gui/pm-gantt/src/outlineRowClick.ts`: the pure click / double-click decision and the drag aria helper (A1, A3, A5).
- Constant `DOUBLE_CLICK_MS` (220): the window in which a second click opens the modal, the same delay that used to postpone selection (A1).
- Function `createOutlineRowClick`: selects on the click, opens on a second click inside the window, and records that id for the toolbar (A1, A2, A3).
- Branch in `click` that returns `ignore` while a title is being edited, so that click does not select (A1, A3).
- Branch in `click` that returns `open` when the same row is clicked again inside the window, without selecting again (A1, A3).
- Function `toolbarTarget`: the id a toolbar action reads at call time, with no timer (A2, A3).
- Function `disarm`: clears the window. The table calls it on long press, an id click, a dependency click, a row double-click, and unmount, so those paths do not open the modal (A1).
- Function `rowDragAttributes`: drops `aria-disabled` when drag is disabled, and leaves the attributes unchanged when drag is enabled (A5).
- Ref `selectedIdRef` and callback `selectRow` in `App.tsx`: the selecting click writes the id the toolbar reads (A2).
- Layout effect in `App.tsx` that copies `selectedId` onto `selectedIdRef`: snapshot load and Hide complete change the selection without a click, and the ref stays the same id.
- Branch in `handleTitleClick` that disarms and runs the dependency-row click when dependency edit is active, instead of selecting or opening (A1).
- Mocks: none.
- Test file `gui/pm-gantt/src/outlineRowClick.test.ts` (new; no earlier test covered this helper), with fake timers:
  - a click selects at once, and the selection is still that row after the window;
  - a second click inside the window opens the modal and does not select again;
  - a click after the window is another select;
  - a click while a title is being edited does not select;
  - a toolbar read immediately after a click is the clicked row's id;
  - a row whose drag is disabled is not marked `aria-disabled`, and the attribute stays when drag is enabled.
