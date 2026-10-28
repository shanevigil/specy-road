# Work-packet brief: `M4.7` — Scriptable graph edits: apply a change file with dry run, acceptance at creation, display-id dependencies `graph-apply`

_This is a deterministic compilation of every artifact the implementer needs. Read top to bottom._

## 1. Execution target

- **Node id:** `M4.7`
- **Title:** Scriptable graph edits: apply a change file with dry run, acceptance at creation, display-id dependencies
- **Codename:** `graph-apply`
- **Type:** task
- **Status (own):** Not Started
- **Status (rollup):** Not Started
- **Execution (milestone hint):** Agentic-led
- **Touch zones:** specy_road/bundled_scripts/roadmap_crud_argparse.py, specy_road/bundled_scripts/roadmap_crud_ops.py, specy_road/bundled_scripts/roadmap_crud_dependency_ops.py, specy_road/bundled_scripts/session_plan.py, specy_road/cli.py, specy_road/cli_usage.py, docs/roadmap-authoring.md, tests/

### Goal

A large roadmap change can be rehearsed and applied as one validated batch.

### Acceptance criteria

- **A1:** `specy-road apply changes.yaml --dry-run` validates the whole batch (add-node, edit-node, add-dependency entries) and prints the resulting ready/blocked waves without writing
- **A2:** Without --dry-run the batch is applied atomically or not at all
- **A3:** `add-node --acceptance` is repeatable; `--dependency` and `add-dependency` accept display ids and store node_keys

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

### This node's planning sheet: `planning/M4.7_graph-apply_d1ffe271-ef17-495a-90de-74a35990666e.md`

## Intent

A large roadmap change can be rehearsed and applied as one validated batch.

## Approach

Build on the transactional writers the CRUD ops already use: stage every change against an in-memory graph, validate, then write. The wave preview reuses session_plan.

## Tasks / checklist

- [ ] apply command with dry run
- [ ] add-node --acceptance
- [ ] display-id dependencies
- [ ] Tests

## References

- `docs/design-notes/v0-3-1-rc1-adopter-feedback-triage.md`
- `docs/roadmap-authoring.md`

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

The PM listed these touch zones: `specy_road/bundled_scripts/roadmap_crud_argparse.py`, `specy_road/bundled_scripts/roadmap_crud_ops.py`, `specy_road/bundled_scripts/roadmap_crud_dependency_ops.py`, `specy_road/bundled_scripts/session_plan.py`, `specy_road/cli.py`, `specy_road/cli_usage.py`, `docs/roadmap-authoring.md`, `tests/`.

**TODO (DEV agent):** confirm these touch zones are accurate by scanning the codebase. Add or remove zones as appropriate, then report the final list in your implementation summary.

## 8. Rollup semantics (reference)

- Ancestor `rollup_status` is computed from leaf descendants.
- A non-leaf is `Complete` only when every leaf descendant is `Complete`.
- Otherwise the ancestor inherits the most pressing non-complete status (`Blocked` > `In Progress` > `Not Started`).
- Pickup targets actionable leaves; ancestors are context-only.

## 9. History (derived from git)

**Planning sheet**: revised in 1 commit; most recent `db6ae4f3`.
