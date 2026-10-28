# Work-packet brief: `M4.8` — list-nodes --json, refresh-stubs --diff, move-node zone rewrite `graph-listing-and-moves`

_This is a deterministic compilation of every artifact the implementer needs. Read top to bottom._

## 1. Execution target

- **Node id:** `M4.8`
- **Title:** list-nodes --json, refresh-stubs --diff, move-node zone rewrite
- **Codename:** `graph-listing-and-moves`
- **Type:** task
- **Status (own):** Not Started
- **Status (rollup):** Not Started
- **Execution (milestone hint):** Agentic-led
- **Touch zones:** specy_road/bundled_scripts/roadmap_crud_ops.py, specy_road/bundled_scripts/roadmap_crud_argparse.py, specy_road/bundled_scripts/refresh_stubs.py, specy_road/bundled_scripts/roadmap_move_node.py, docs/pm-workflow.md, tests/

### Goal

Listing is scriptable, stub refreshes are previewable, and renumbering does not strand touch zones.

### Acceptance criteria

- **A1:** `list-nodes --json` emits the full node list without title truncation
- **A2:** `refresh-stubs --diff` shows the managed-block and skill changes before writing
- **A3:** move-node rewrites touch-zone path segments that equal the old display id
- **A4:** `finish-this-task` in merge mode can delete the merged feature branch locally and on the remote (`--delete-branch`), and `specy-road branches prune` lists or deletes merged feature/rm-* branches

## 2. Ancestor context chain

- **M4** (phase) — Brainstorm and roadmap editing features _(rollup: Not Started)_

## 3. Planning context (inlined)

### Ancestor planning sheet: `planning/M4_brainstorm-editing-features_4e85b231-476a-4c86-89a2-9c224c0dfbf9.md`

## Intent

The larger requests from rc1 adopters: promote carries the converge judgement into the graph, batch input, structured placement, decisions, repo evidence and scriptable graph editing.

## Approach

Leaves under this phase are picked by agents through the task loop; each leaf's sheet cites the triage note row it closes.

## Tasks / checklist

- [ ] Every leaf Complete through the review gate

## References

- `docs/design-notes/v0-3-1-rc1-adopter-feedback-triage.md`

### This node's planning sheet: `planning/M4.8_graph-listing-and-moves_b7f094e3-dce5-4ab0-9e14-e00f8f412609.md`

## Intent

Listing is scriptable, stub refreshes are previewable, and renumbering does not strand touch zones.

## Approach

Three independent small changes; keep each in its own commit.

## Tasks / checklist

- [ ] --json
- [ ] --diff
- [ ] zone rewrite
- [ ] Tests
- [ ] branch cleanup after finish

## References

- `docs/design-notes/v0-3-1-rc1-adopter-feedback-triage.md`

## 4. Shared contracts (cited)

### `shared/README.md`

# Shared contracts

Place specifications, API shapes, and policies here, and **cite** them from a node's planning sheet under `## References` instead of duplicating intent in chat.

`specy-road brief` always inlines this README, then only the contracts the node's chain cites by filename. Everything else here is listed as a path with a `specy-road search "<query>" --kind shared` pointer — so keep this file a real index of what lives here, and prefer one topic per file.

Add Markdown or other tracked artifacts as your project grows.

## 5. Dependencies (must complete first)

- _none_

## 6. Dependency context (intent of upstream work)

_**Effective** dependencies below — this node's explicit `dependencies` plus every dependency inherited from an ancestor (same set the do-next-available-task picker uses). Each is **part of the brief on purpose** — do not ask the PM to repeat any of this prose inside this task's planning sheet. If something here is unclear or insufficient for this specific task, add a one-line clarification under `## Approach` (or `## Decisions and notes` for gates) citing the dep by display id._

- _no effective dependencies_

## 7. Touch zones — implementing agent instruction

The PM listed these touch zones: `specy_road/bundled_scripts/roadmap_crud_ops.py`, `specy_road/bundled_scripts/roadmap_crud_argparse.py`, `specy_road/bundled_scripts/refresh_stubs.py`, `specy_road/bundled_scripts/roadmap_move_node.py`, `docs/pm-workflow.md`, `tests/`.

**TODO (DEV agent):** confirm these touch zones are accurate by scanning the codebase. Add or remove zones as appropriate, then report the final list in your implementation summary.

## 8. Rollup semantics (reference)

- Ancestor `rollup_status` is computed from leaf descendants.
- A non-leaf is `Complete` only when every leaf descendant is `Complete`.
- Otherwise the ancestor inherits the most pressing non-complete status (`Blocked` > `In Progress` > `Not Started`).
- Pickup targets actionable leaves; ancestors are context-only.

## 9. History (derived from git)

**Planning sheet**: revised in 2 commits; most recent `db6ae4f3`, `c5db7c3e`.
