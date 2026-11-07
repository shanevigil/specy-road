# Implementation summary: M17.11 (gui-acceptance-editing)

Commits `1e0e92f2` (feature) and the fix-round commit after it, on `feature/rm-gui-acceptance-editing`.

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
- **A2:** `acceptanceEdit.test.ts` has 17 rows: unchanged, added, removed, reordered, emptied, trimmed or
  whitespace-only dropped, and one refusal row for each of the 11 line boundaries. `editModalSaveQueue.test.ts` has two queue rows:
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

## Fix round 1 (review `gpt-6.1-sol`, R1)

- **Class:** a line boundary inside one criterion that the server's parser splits on but the dialog
  did not refuse. `_nonempty_lines` uses Python's `str.splitlines()`, which splits on LF, VT, FF, CR,
  CR LF, FS, GS, RS, NEL, LS and PS. The dialog refused only CR and LF, so a pasted U+2028 or U+2029
  reached the PATCH and the server split it into separate criteria without warning.
- **Fix (design, not an instance patch):** `acceptanceEdit.ts` now has one table, `LINE_BOUNDARY`, which
  is exactly the `str.splitlines()` set; the docstring states that rule. It is the only check on the save
  path, and it uses the existing refusal message. The refusal test is parametrized over all 11 boundaries
  (CR LF included). The static assets were rebuilt.
- The branch was merged with `origin/WIP/improvements-0-3-1` first; the merge had no conflicts.

## Probes

- The full `str.splitlines()` set, enumerated over every code point in Python, is exactly
  `\n \v \f \r \x1c \x1d \x1e \x85 \u2028 \u2029`. Result: `LINE_BOUNDARY` covers each of them,
  and the vitest rows pass for each.
- The server's parser: `_nonempty_lines("a\u2028b")` returns `['a', 'b']`, which confirms the reported
  split. Result: the dialog now refuses that value before any PATCH.
- Other routes into the PATCH value: `onAcceptanceInput` is the only caller of `saveQueue.setAcceptance`.
  Add, remove and move all go through it, and each passes only existing or empty rows. Result: every
  route reaches the same check.
- Stored criteria that already contain a boundary (a hand-edited JSON file): the dialog loads them as is.
  Any later edit is refused with the message until that row is fixed, so nothing is split without a
  warning. Result: no change needed.
- Trim mismatch (`trim()` in JS against `strip()` in Python), which is broader than R1. Python strips
  `\x1f` and JS does not; JS trims `\ufeff` and Python does not. Neither one splits a criterion. A
  criterion made only of `\x1f` would be sent and then dropped by the server, which shifts later A-numbers
  by one. I left this unfixed because it is outside the reviewed class; it is listed here for the
  coordinator.

## Added

- `acceptanceEdit.ts` `acceptanceEdit()` and `ACCEPTANCE_NEWLINE_MESSAGE`: a pure helper that builds the
  PATCH value and refuses a line break (A1, A2).
- `acceptanceEdit.ts` `LINE_BOUNDARY` table (the Python `str.splitlines()` set): the server would split a
  criterion on any of these boundaries (fix round 1, R1).
- `EditModal.tsx` `AcceptanceSection` component: the per-criterion fields and their add, remove and move
  controls (A1).
- `EditModal.tsx` `acceptanceDraft` and `acceptanceErr` state, and `onAcceptanceInput`, with a guard that
  matches the title's (`!node || !hydrated || readOnlyCheckout`): it feeds the queue and shows refusals.
- `editModalSaveQueue.ts` `"acceptance"` save kind, `SaveSnapshot.acceptance` and `setAcceptance()`:
  acceptance saves go through the same ordered, debounced queue as the other fields.
- `types.ts` `RoadmapNode.acceptance?: string[]`: read from `GET /api/roadmap` (A1).
- Test `acceptanceEdit.test.ts` (17 rows): the A2 helper rows, with the refusal row parametrized over
  every `str.splitlines()` boundary.
- Test rows in `editModalSaveQueue.test.ts`, "saves acceptance as one pair next to an unrelated title edit"
  and "sends no acceptance PATCH for an unchanged or reverted list": the A2 queue rows. The harness
  snapshot gains `acceptance: "a\nb"`.
- Test `test_api_patch_acceptance_reads_back`: the A3 contract test (set, read back, then clear with `''`).
- Mocks: none new (reuses the existing queue harness).
