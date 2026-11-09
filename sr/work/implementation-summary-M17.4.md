# Implementation summary: M17.4 — per-leaf orchestration detail (`gui-orch-leaf-detail`)

## What changed

- **`gui/pm-gantt/src/orchestrationSnapshot.ts`**: review rows follow `fresh_for_head` only (`true` → fresh, `false` → stale, `"unknown"` → unknown, absent or null → —). A review commit is never compared with `READY.commit`. Verdict `block` sorts first; every other verdict keeps snapshot order. READY's displayed commit is the first 12 characters (`unknown` and any shorter value stay as stored). Worktree dirty is `yes` / `no` / `unknown` / — (a missing ahead or behind stays —, never 0). `blocked_on` stays plain `A<n>: <reason>` text. A null hold reason stays —.
- **`gui/pm-gantt/src/components/LeafOrchestrationDetail.tsx`** (new): one read-only view of a single leaf's view-model group. It shows the claim (or —); each worktree (path, branch, dirty, ahead, behind, with a line that ahead and behind are against the integration branch); the READY short commit, model and age, then one plain-text line per `blocked_on` entry; each review (model, verdict, full commit, fresh for HEAD); the gate (state, approvals, blocks, fresh for HEAD); and holds (source, id, reason). A hold-list source is labelled "hold list"; a gate's id is the gate id and its reason is the snapshot reason (M17.6 stores the gate title there). The copy button's title is `copyCommand("handoff status", displayId)` and the click only asks the parent to write that command to the clipboard.
- **`LeafOrchestrationSection`** in the same file: the edit modal's collapsed `<details>` "Orchestration". It loads when opened (the same dev `?mock=orchestration` switch as the drawer, otherwise `fetchOrchestration`) and does not poll or save. A 404 uses the drawer's unavailable sentence. A leaf key missing from the snapshot says there is no orchestration state for it.
- **`gui/pm-gantt/src/components/OrchestrationDrawer.tsx`**: each leaf header gains a Detail control. The selected leaf (the control, or `filterLeafId` when the drawer opens or the filter changes) mounts `LeafOrchestrationDetail` under that group. The drawer's existing copy handler writes the clipboard. The worker table, leaf-id link, worker link, poll and `filterLeafId` behaviour are unchanged. The dev mock loader moved into `loadDisplayedOrchestration` so the modal uses the same switch; the drawer still imports only `fetchOrchestration` from `api.ts`.
- **`gui/pm-gantt/src/components/EditModal.tsx`**: for a node with no child in `allNodes`, a collapsed read-only Orchestration section sits between the fields and the planning sheet. Save-queue calls, status, acceptance and planning writes are untouched.
- **`specy_road/pm_gantt_static/`**: rebuilt by `npm run build`.

## Touch zones (final)

Changed: `LeafOrchestrationDetail.tsx`, `OrchestrationDrawer.tsx`, `EditModal.tsx`, `orchestrationSnapshot.ts`, `orchestrationSnapshot.test.ts`, `specy_road/pm_gantt_static/`.

Zoned but unchanged: `gui/pm-gantt/src/App.css`. It is the unused Vite starter stylesheet; `main.tsx` loads `index.css` only, and importing `App.css` would ship those starter rules. The detail reuses classes the drawer already uses (`worker-detail`, `worker-section-title`, `workspace-file-table`, `outline-meta`, `workspace-empty`, `worker-group`), so `index.css` did not need an edit. No path outside the zones was needed.

## Verification

- `cd gui/pm-gantt && npm ci && npm run lint && npm test && npm run build`: lint 0 errors (42 warnings, all pre-existing; none in the new file or in `OrchestrationDrawer.tsx`), 30 files / 305 tests pass, build succeeds.
- No browser tools in this session. The detail is covered by the view-model rows and the production build; a click-through of the drawer and the edit modal was not run.

## Accepted limits

- There is no DOM test. The component's mount, the collapsed section and the clipboard button are for review, M17.8 and M17.9. The view-model rows pin freshness, order, missing fields and the short READY commit.
- A gate hold with a null reason shows — rather than a title looked up from the outline. A2 requires null to stay —. The id column is the gate id; the title appears when the snapshot puts it in `reason`.
- The drawer shows the claim on the group header and again inside the detail, so the same component is complete in the edit modal.

## Added

- `shortCommit`: READY's displayed commit is 12 characters; `unknown` and shorter values are not cut. Freshness does not read it.
- `reviewsBlockingFirst`: verdict `block` first, snapshot order otherwise. Freshness is not an input.
- `loadDisplayedOrchestration`: one dev-mock / live GET path for the drawer and the edit-modal section.
- `sourceLabel`: the hold-list source reads "hold list" in the detail.
- `CellTable`: one table for worktrees, reviews and holds.
- `LeafOrchestrationDetail`: the shared read-only detail.
- `LeafOrchestrationSection`: the collapsed edit-modal mount.
- Branch: the edit modal renders the section only when no outline node has this node's id as `parent_id`.
- Branch: the drawer mounts the detail only for the selected leaf key.
- Branch: opening the drawer or changing `filterLeafId` selects that leaf (null clears the selection).
- Guard: the section's fetch sets state only while `live` is true, so closing the section before the response returns does not update state.
- Branch: opening the section clears the previous load, and a snapshot with no row for this leaf says so.
- Branch: the section's copy handler shows "copy failed" when `navigator.clipboard` is missing or refuses the write. It calls `copyCommand` and writes that string; it does not send a request.
- Mocks: none.
- Test (extended schema 1 row): the review is fresh from `fresh_for_head` with no READY to compare, and dirty false is `no` while omitted ahead/behind stay —.
- Test (new row): a fresh approval whose commit differs from READY stays fresh, a block on READY's own commit stays stale and lists first, an unknown review stays unknown, and READY's commit is the 12-character form, not the review commit.
- Test (updated mock row): the two worktrees read dirty `yes` and `no`. The ahead/behind numbers are the same check as before.
