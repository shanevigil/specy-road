# Implementation summary for M1.1

## Summary

The scaffold placeholders this task exists to replace had already been replaced in `sr/` before the leaf was picked up, so the work is verification plus ticking the planning-sheet checklists. A1–A4 hold at base `37a0078`; A5 is still open (see Verification) and is to be re-checked by the coordinator once the overlapping in-flight claims land.

- **A1** — `constitution/purpose.md` and `constitution/principles.md` describe specy-road (the coordination kit and its nine principles), not the template.
- **A2** — `vision.md` is one paragraph on the desired future state of the toolkit.
- **A3** — `roadmap/git-workflow.yaml` sets `integration_branch: WIP/improvements-0-3-1` and `remote: origin`; `on_complete: merge` and `require_implementation_review_before_finish: true` are set explicitly.
- **A4** — real phases M2–M6 are in `roadmap/manifest.json`, each with a planning sheet under `planning/`. M1 is kept as the record of adoption rather than retitled.
- **A5** — open. `export --check` passes. `digest --check` drifts only by the `M1.1 on feature/rm-project-setup` claim row that registration adds; `finish-this-task` regenerates and commits `roadmap-context.md`. `validate --strict` fails on warnings only (below).

## Changes

- `planning/M1.1_project-setup_b2c3d4e5-f6a7-4890-b123-456789abcdef.md`: ticked the purpose, principles, vision, git-workflow and first-real-phase items. Left unticked: the optional `specyrd init` item (no stub pack is installed in `sr/`; `refresh-stubs` reports "managed blocks only") and the export/digest/`--strict` item (A5, pending).
- `planning/M1_adopt-specy-road_a1b2c3d4-e5f6-4789-a012-3456789abcde.md`: ticked "Retitle this phase, or add the next one" (M2–M6 added). Left "Complete the setup task under this phase" unticked: it is true only once M1.1 finishes.
- `AGENTS.md` (outside the touch zones, not changed on this branch): its managed block was stale against the WIP line, which made `validate --strict` warn. The coordinator refreshed it on the WIP in `f9fc344` (one line, Load order item 0: run `brainstorm start` first when brainstorming); this branch fast-forwarded to it.

Touch zones: `constitution/`, `vision.md`, `roadmap/`, `planning/` are accurate for the task as written; this run changed `planning/` only. `AGENTS.md` and the generated `roadmap.md` / `roadmap-context.md` sit at the project root outside them; the first was handled on the WIP, the second by `finish-this-task`.

## Verification

Run from the checkout root with `sr/tools/specy-road` (resolves `sr/` from `.specyrd/manifest.json`), at `f9fc344` plus the checklist edits:

- `specy-road validate --strict`: `OK: roadmap and registry validate.`, then `FAILED (--strict)` on 26 warnings, all `registry: possible overlap` between other in-flight claims (worker-cli-fixes, stale-command-check, context-budget-meter, branch-cleanup, context-regression-set). None involves M1.1. Before `f9fc344` there were 27; the extra one was the stale `AGENTS.md` block.
- `specy-road export --check`: `OK: roadmap.md matches merged roadmap graph.`
- `specy-road digest --check`: drift; `digest -o -` differs from the committed file only by `- \`M1.1\` on \`feature/rm-project-setup\` since 2026-10-28`.
- No code changed, so no `pytest` run.

## Added

### Helpers
none

### Branches or guards
none

### Mocks
none

### Tests
none
