# Implementation summary: M17.12 `gui-group-siblings-action`

## What changed

- `gui/pm-gantt/src/outlineGroup.ts` (new, pure): `groupDialogState(orderedIds, byId, rowId)` gives the
  dialog's opening state. It holds the row's siblings in the loaded outline's order (`ordered_ids` filtered
  by parent), with only the row checked. The new parent id is one past the highest child number of the parent
  (`Mk` at the root), so gaps are kept. The title is empty, the type is `milestone` and `rewriteRefs` is
  false. `groupBody(state)` builds `GroupOutlineBody`'s `{into_new, title, node_ids, type, rewrite_refs}`
  with the checked ids in outline order. It refuses an empty or whitespace-only title and a state with no
  row checked, and the title is sent trimmed. `GROUP_TYPES` lists milestone, phase and task: the server
  refuses a gate parent.
- `gui/pm-gantt/src/api.ts`: `groupOutline(body)` sends one `POST /api/outline/group` with the PM write
  header (`X-PM-Gui-Fingerprint`) through the existing `pmGuiMutationHeaders` and `throwIfMutationFailed`.
  A 400 throws an `Error` whose message is the server's detail.
- `gui/pm-gantt/src/components/GroupSiblingsModal.tsx` (new): the dialog, built on `ModalFrame` with the
  Publish dialog's existing classes. It has sibling checkboxes, an editable new parent id, a required title,
  a type select and "Rewrite id references in prose". A local refusal or the server's refusal shows in the
  dialog (`e.message`, verbatim), and the dialog stays open.
- `gui/pm-gantt/src/App.tsx`:
  - A toolbar button **Group siblings…** sits after Outdent. Like Indent, Outdent, Add and Delete, it is
    gated by `guardRowAction` on the selected row.
  - `submitGroup` runs `groupOutline` through `performOptimisticMutation`, as the move action does: the
    pending pulse on the grouped rows (kind `move`), the transparent retry on a retryable 412
    (`runMutationWithAutoffRetry`), then `loadSnapshot`.
  - The optimistic op is `null`, so nothing in the outline changes before the server answers, and nothing
    changes on a refusal.
  - On success the new parent (`into_new`) is selected. On an unrecoverable 412 the app's existing "changed
    elsewhere" banner shows and the dialog closes.
  - The dialog's opening state comes from `data` (server truth), not `displayData`, so an in-flight add
    placeholder never counts as a sibling or feeds the default id.
- `specy_road/pm_gantt_static/`: rebuilt with `npm run build`.
- `tests/test_gui_outline_contract.py`: one new test, below. The existing tests are unchanged (the diff only
  adds lines).
- `docs/pm-gui.md`: a "Group siblings" bullet. `CHANGELOG.md`: an `[Unreleased]` / Added entry.

## Decisions

- **Placement:** the action is a toolbar button acting on the selected row, beside the other selected-row
  outline actions (indent, outdent, add, delete). The outline table has no per-row action menu to extend.
- **Conflict (unrecoverable 412):** handled as the move action handles it (the view is refreshed and the
  app banner shows), and the dialog closes, because the ids it holds may no longer be current.
- **Default id:** one past the highest number among the siblings' ids that are `parent.k`. A sibling whose
  id an edge-only re-parent kept (for example `M1.3` under `M2`) does not count. A clash with an archived id
  is left to the server's 400, as the coordinator resolution says.

## Touch zones

All edits are inside the listed zones. Three listed zones were not changed:

- `gui/pm-gantt/src/components/OutlineTable.tsx`: the action is on the toolbar, so the table needed no change.
- `gui/pm-gantt/src/usePmGuiHandlers.ts`: no new context handler was needed.
- `gui/pm-gantt/src/App.css`: nothing imports it (only `index.css` is imported, by `main.tsx`), so styles
  there would not apply. The dialog reuses existing classes from `index.css`, which is outside the zones.

No change was needed outside the zones. File limits are OK; the TypeScript files are not in their globs.

## Verification

- `cd gui/pm-gantt && npm ci && npm run lint && npm test && npm run build`: pass. Lint reports 0 errors and
  no new warnings (the 8 warnings in `App.tsx` are on lines that were already there). Vitest: 28 files, 240
  tests.
- `python -m pytest tests/test_gui_outline_contract.py`: 46 passed.
- Full suite `pytest -n 4`: 6881 passed, 9 skipped, 1 failed before the commit. The failure was
  `test_lean_gates.py::test_machine_paths_pass_on_this_repo`, which read a tracked static asset that the
  uncommitted rebuild had deleted. It passes after the commit (re-run with `test_verify_wheel_contents.py`:
  51 passed).
- `specy-road file-limits`: OK.
- Not checked in a browser: no browser automation was available in this session. The dialog's logic is
  covered by the vitest rows over `outlineGroup.ts`, and the request by the contract test.
- A4 (informational): about +314 frontend lines (App 53, api 11, dialog 152, helper 98), +75 vitest,
  +29 pytest and +6 docs and CHANGELOG lines.

## Added

- Module `gui/pm-gantt/src/outlineGroup.ts`: the pure dialog logic A2 asks for.
- Function `groupDialogState`: the row's siblings in outline order, the row checked, and the default id,
  title, type and rewrite flag (A1).
- Function `groupBody`: builds the request body from the dialog state, with checked ids in outline order (A1, A2).
- Branch in `groupBody` refusing an empty or whitespace-only title (A2); constant `GROUP_TITLE_MESSAGE`.
- Branch in `groupBody` refusing a state with no row checked (A2); constant `GROUP_NONE_CHECKED_MESSAGE`.
- Private helper `nextChildId`: one past the highest child number, gaps kept (A1, the coordinator resolution).
- Filter in `nextChildId` that skips a sibling whose id is not `parent.k`: an edge-only re-parent keeps its
  old id, which would otherwise give a default under the wrong parent. A vitest row reaches it.
- Constant `GROUP_TYPES`: the dialog's type options, without gate, which the server refuses.
- Type `GroupOutlineBody`: mirrors the server's model and is used by `groupBody` and `groupOutline`.
- Function `groupOutline` in `api.ts`: the one POST A1 names.
- Component `GroupSiblingsModal`: the dialog (A1, A2).
- App state `groupRowId`, callback `submitGroup` and the toolbar button: open the dialog, send through
  `performOptimisticMutation`, and select the new parent on success (A1, A2).
- Flag object `sent` in `submitGroup`: `performOptimisticMutation` resolves on an unrecoverable 412 as well
  as on success, so the flag records whether the POST succeeded before the new parent is selected.
- Mocks: none.
- Test file `gui/pm-gantt/src/outlineGroup.test.ts` (new; no earlier test covered this helper):
  - siblings and default id for a leaf (`M1.4`), a gap (`M1.2.5`) and the root (`M3`), plus the opening
    defaults;
  - an edge-only re-parent sibling ignored (`M2.2`);
  - the body in outline order with the title trimmed, which is the body the contract test posts;
  - edited id, type and rewrite_refs passed through;
  - refusals for an empty title, a whitespace-only title and no row checked.
- Test `test_outline_group_posts_the_dialogs_body` (contract): posts the body the vitest row pins on
  `wide_fixture`. A taken id (`M1.2`) answers 400 with the exact detail and the tree unchanged. The body
  itself answers 200, and M1.4 holds M1.1 and M1.3 in that order (A3).
