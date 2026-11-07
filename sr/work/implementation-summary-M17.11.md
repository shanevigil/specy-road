# Implementation summary: M17.11 (gui-acceptance-editing)

Commit `1e0e92f2` on `feature/rm-gui-acceptance-editing`.

## What changed

- **A1:** `EditModal.tsx` gains an **Acceptance** section (`AcceptanceSection`, in the same file): one
  one-row textarea per criterion, with move up, move down, remove, and "Add criterion". Each edit goes
  through `acceptanceEdit()` and then `saveQueue.setAcceptance(value)`. The value is the criteria trimmed,
  with empty ones dropped, joined by `\n`. The queue sends `PATCH /api/nodes/{id}` with the one pair
  `{key: "acceptance", value}` through `patchNode()` (same fingerprint header and 412 retry as the other
  fields; the milestone lock is the PATCH route's existing server-side guard). A criterion containing
  `\n` or `\r` is refused: the draft is not changed and a `role="alert"` message is shown. The section is
  read-only under `readOnlyCheckout` and before hydration, like the title, and the read-only note now
  names it. `RoadmapNode` gains `acceptance?: string[]`, which is hydrated on open from the node that
  `GET /api/roadmap` returned. No server, route or body change.
- **Save queue:** `editModalSaveQueue.ts` gains a fourth kind, `"acceptance"` (label "Acceptance", 500 ms
  debounce, order title, status, acceptance, sheet), plus `SaveSnapshot.acceptance` and `setAcceptance()`.
  The queue's existing dedupe means an unchanged or reverted list sends no PATCH.
- **A2:** `acceptanceEdit.test.ts` has 8 rows: unchanged, added, removed, reordered, emptied, trimmed or
  whitespace-only dropped, and refused (`\n` and `\r`). `editModalSaveQueue.test.ts` has two queue rows:
  acceptance saved as one pair next to a title edit (one PATCH at a time, with a refresh between), and
  an unchanged or reverted list (no PATCH).
- **A3:** `tests/test_gui_app_mutations.py::test_api_patch_acceptance_reads_back` PATCHes the helper's
  value on a dogfood copy and reads it back through `GET /api/roadmap`. It then PATCHes `''` and checks
  that the field is gone. `npm ci && npm run lint && npm test && npm run build` passed (lint: 0 errors,
  and the new warnings follow the file's existing set-state-in-effect pattern). `specy_road/pm_gantt_static/`
  has been rebuilt.
- **A5 / docs:** `docs/pm-gui.md` gains a "Node edit dialog" entry under *What ships*. The doc had no
  edit-dialog entry before. The entry says that GUI edits change the graph only and that Publish (or
  `export` and `digest`) regenerates `roadmap.md` and `roadmap-context.md`. `CHANGELOG.md` has an
  [Unreleased] Added entry.

## Touch zones (final)

Used: `EditModal.tsx`, `editModalSaveQueue.ts`, `editModalSaveQueue.test.ts`, `acceptanceEdit.ts`,
`acceptanceEdit.test.ts`, `types.ts`, `specy_road/pm_gantt_static/`, `tests/test_gui_app_mutations.py`,
`docs/pm-gui.md`, `CHANGELOG.md`.
Not needed: `api.ts` (the existing `patchNode` is reused) and `App.css`. `App.css` is not imported
anywhere (the app imports only `index.css`, which is outside the zones), so the section reuses existing
classes (`modal-edit-title-wrap`, `modal-edit-title-label`, `modal-edit-title-error`, `outline-meta`)
plus a few inline layout styles.

## Notes

- A criterion has no id, so rows are keyed by position (the eslint `no-array-index-key` warning is
  disabled on that line with a reason).
- The draft is hydrated when a node is opened, not on every roadmap refresh, matching how the title
  is handled.
- Accepted limit from the sheet: reordering renumbers A1..An, and the dialog does not warn about it.

## Added

- `acceptanceEdit.ts` `acceptanceEdit()` and `ACCEPTANCE_NEWLINE_MESSAGE`: a pure helper that builds the
  PATCH value and refuses a line break (A1, A2).
- `acceptanceEdit.ts` line-break guard (`/[\r\n]/`): a newline would split one criterion in two on the
  server.
- `EditModal.tsx` `AcceptanceSection` component: the per-criterion fields and their add, remove and move
  controls (A1).
- `EditModal.tsx` `acceptanceDraft` and `acceptanceErr` state, and `onAcceptanceInput`, with a guard that
  matches the title's (`!node || !hydrated || readOnlyCheckout`): it feeds the queue and shows refusals.
- `editModalSaveQueue.ts` `"acceptance"` save kind, `SaveSnapshot.acceptance` and `setAcceptance()`:
  acceptance saves go through the same ordered, debounced queue as the other fields.
- `types.ts` `RoadmapNode.acceptance?: string[]`: read from `GET /api/roadmap` (A1).
- Test `acceptanceEdit.test.ts` (8 rows): the A2 helper rows.
- Test rows in `editModalSaveQueue.test.ts`, "saves acceptance as one pair next to an unrelated title edit"
  and "sends no acceptance PATCH for an unchanged or reverted list": the A2 queue rows. The harness
  snapshot gains `acceptance: "a\nb"`.
- Test `test_api_patch_acceptance_reads_back`: the A3 contract test (set, read back, then clear with `''`).
- Mocks: none new (reuses the existing queue harness).
