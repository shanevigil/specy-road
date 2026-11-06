## Intent

0.3.2 makes orchestration visible: the PM GUI shows workers, claims, reviews and worktrees for each leaf. It was moved out of M16 by the maintainer (2026-11-05): M16 delivers only the read-only orchestration snapshot interface (M16.3.1) and the folded PM UI server (M16.3.7) that this phase builds on.

## Approach

- The GUI reads only `specy_road.orchestration`'s snapshot, whose fields are fixed by tests/fixtures/orchestration_snapshot_v1.json (`schema: 1`). It imports no worker_* or gui_app_routes_workers internals; a field the GUI needs that the snapshot lacks is a change to the snapshot interface with a new schema number, not a side import.
- This phase owns the existing sections of docs/pm-gui.md (M16.6.1 only appends sections for brainstorm and LLM review).
- M17.1 is a placeholder the maintainer turns into dispatchable leaves after M16.3.1 and M16.3.7 merge; nothing in this phase starts before that.

## Tasks / checklist

- [ ] M17.1 — 0.3.2 PM GUI orchestration and worktree view: plan from the snapshot interface

## References

- M16.3.1 (snapshot interface and v1 fixture), M16.3.7 (PM UI server fold)
- `sr/docs/research/slimming-2026-11-05/RECOMMENDATION.md` section 3.1 (D1)
- No `shared/` contract applies.
