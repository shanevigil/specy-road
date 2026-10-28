# Work-packet brief: `M3.3` — Document the canonical chunk key order and offer a deliberate normalisation `chunk-key-order`

_This is a deterministic compilation of every artifact the implementer needs. Read top to bottom._

## 1. Execution target

- **Node id:** `M3.3`
- **Title:** Document the canonical chunk key order and offer a deliberate normalisation
- **Codename:** `chunk-key-order`
- **Type:** task
- **Status (own):** Not Started
- **Status (rollup):** Not Started
- **Execution (milestone hint):** Agentic-led
- **Touch zones:** specy_road/bundled_scripts/roadmap_rebalance.py, specy_road/bundled_scripts/roadmap_chunk_utils.py, docs/roadmap-authoring.md, tests/

### Goal

A PM is not surprised when a first edit reorders every node of a hand-authored chunk, and can normalise a chunk on purpose.

### Acceptance criteria

- **A1:** docs/roadmap-authoring.md explains that every write renders chunks in one canonical key order, so the first edit of a hand-authored chunk rewrites all of it and later diffs stay confined
- **A2:** rebalance-chunks --normalize rewrites every chunk in canonical form without moving a node, and is a no-op on already-canonical chunks
- **A3:** A test covers normalize on a hand-ordered chunk and its idempotence

## 2. Ancestor context chain

- **M3** (phase) — 0.3.1 pre-final fixes from rc1 feedback _(rollup: Not Started)_

## 3. Planning context (inlined)

### Ancestor planning sheet: `planning/M3_pre-final-fixes_c78073ae-aaa6-4090-8ed4-1990c307c7e3.md`

## Intent

Every confirmed defect, misleading message and small gap reported against 0.3.1rc1 is fixed before the next release candidate.

## Approach

Leaves under this phase are picked by agents through the task loop; each leaf's sheet cites the triage note row it closes.

## Tasks / checklist

- [ ] Every leaf Complete through the review gate

## References

- `docs/design-notes/v0-3-1-rc1-adopter-feedback-triage.md`

### This node's planning sheet: `planning/M3.3_chunk-key-order_a4cdff1a-4b57-4fc1-9c36-9357c656df78.md`

## Intent

A PM is not surprised when a first edit reorders every node of a hand-authored chunk, and can normalise a chunk on purpose.

## Approach

Keep the canonical order (stable diffs after the first write). Add the flag to rebalance-chunks rather than a new command; it already owns chunk rewriting and the manifest.

## Tasks / checklist

- [ ] Doc paragraph next to the chunk-limit rules
- [ ] `--normalize` flag
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

The PM listed these touch zones: `specy_road/bundled_scripts/roadmap_rebalance.py`, `specy_road/bundled_scripts/roadmap_chunk_utils.py`, `docs/roadmap-authoring.md`, `tests/`.

**TODO (DEV agent):** confirm these touch zones are accurate by scanning the codebase. Add or remove zones as appropriate, then report the final list in your implementation summary.

## 8. Rollup semantics (reference)

- Ancestor `rollup_status` is computed from leaf descendants.
- A non-leaf is `Complete` only when every leaf descendant is `Complete`.
- Otherwise the ancestor inherits the most pressing non-complete status (`Blocked` > `In Progress` > `Not Started`).
- Pickup targets actionable leaves; ancestors are context-only.

## 9. History (derived from git)

**Planning sheet**: revised in 1 commit; most recent `db6ae4f3`.
