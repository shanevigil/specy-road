## Intent

0.3.1 makes orchestration visible in the PM GUI: workers, claims and holds, worktrees and reviews for each leaf, read-only. The maintainer moved this phase from 0.3.2 into 0.3.1 (2026-11-05 evening): it runs largely in parallel with the M16 refactor, because the React code under gui/pm-gantt/ barely overlaps M16's Python work, and the M16.8.9 "ready to tag 0.3.1" gate depends on this phase.

Out of scope for 0.3.1: any GUI action that changes orchestration state (stop or message a worker, prune a worktree, release a claim, approve a review) unless the maintainer names one at M17.1; M18.22's supervision rows (stalled loop, stuck review queue), which come after 0.3.1; changes to the existing Workers drawer beyond a link into it.

## Release map

| Release | What it contains |
| --- | --- |
| rc4 | M21 (rc4 stabilization) |
| rc5 | M16 (lean core) + M22 (rc5 fixes) |
| 0.3.1 | the M16.8.9 "ready to tag 0.3.1" gate + M17 (PM GUI orchestration view, built in parallel with M16) + the rc5 fixes; then the maintainer's tag (gate M16.8.10) |
| after 0.3.1 | M18, M19, M20 (each depends on gate M16.8.10, "0.3.1 tagged") |

Milestone numbers are not release order; dependencies are. (Maintainer ruling, 2026-11-05 evening.)

## Approach

- **Two lanes.** Frontend leaves (M17.2-M17.5) start as soon as the maintainer clears the M17.1 design gate: they build against a mock snapshot under gui/pm-gantt/src/fixtures/ whose required fields mirror M16.3.1's v1 field list, and test only pure view-model code with vitest. Backend leaves wait for M16's code chain: M17.6 (snapshot schema 2: the optional fields the panels need) on M16.3.1, M17.7 (`GET /api/orchestration`) on M16.3.7 and M17.6. M17.8 joins the lanes (docs, CHANGELOG, live wiring); M17.9 is the coordinator's GUI acceptance run on the agentic sandbox.
- **One read path.** The GUI reads only `specy_road.orchestration`'s snapshot (`orchestration.state.snapshot(repo_root)`, v1 fixture tests/fixtures/orchestration_snapshot_v1.json committed by M16.3.1). It imports no worker_* or gui_app_routes_workers internals; a field the GUI needs that the snapshot lacks is a snapshot change with a new schema number (M17.6), not a side import.
- **Compatibility.** Every existing `/api/` route keeps its response shape; the new route is additive; schema 2 only adds optional fields; a GUI served by an older server (404 on `/api/orchestration`) looks exactly as it does today. Contract tests (M17.7) tie the GUI mock, the server fixture and the route together.
- **Read-only first.** No mutating action in 0.3.1 unless the maintainer names one at M17.1; it would then be its own leaf calling the CLI's existing command.
- **Docs.** This phase owns docs/pm-gui.md's existing sections (M16.6.1 only appends brainstorm and LLM-review sections).
- **Testing on the sandbox.** M17.9 runs a scripted browser test on an agentic-sandbox VM (MCP tools claim_workspace, vm_start, sbvm_exec, sbvm_run_browser_test, sbvm_screenshot) against a built wheel and a seeded fixture repo. The coordinator runs it, not CI and not a worker, and asks the maintainer before using the sandbox.

## Tasks / checklist

- [ ] M17.1 — Gate: maintainer signs off the information design and the read-only scope
- [ ] M17.2 — Snapshot types, mock snapshot and view model (frontend, after M17.1)
- [ ] M17.3 — Orchestration drawer: workers per leaf (frontend)
- [ ] M17.4 — Leaf detail: worktrees, READY, reviews, gate state (frontend)
- [ ] M17.5 — Outline badges for claims, holds and review state (frontend)
- [ ] M17.6 — Snapshot schema 2 (backend, after M16.3.1)
- [ ] M17.7 — `GET /api/orchestration` and contract tests (backend, after M16.3.7)
- [ ] M17.8 — Docs, CHANGELOG and live wiring
- [ ] M17.9 — GUI acceptance on the agentic sandbox (coordinator)

## References

- M16.3.1 (snapshot fields, status vocabulary, v1 fixture), M16.3.7 (PM UI server fold), M16.6.1 (docs/pm-gui.md appends)
- docs/pm-gui.md (Workers drawer, read-only JSON API), specy_road/gui_app_routes_workers.py, gui/pm-gantt/src/components/WorkersDrawer.tsx
- M18.22 (supervision rows the GUI may show after 0.3.1)
- `sr/docs/research/slimming-2026-11-05/RECOMMENDATION.md` section 3.1 (D1)
- No `shared/` contract applies.
