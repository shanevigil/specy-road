# Work-packet brief: `M3.2` — handoff status reports review records without a claim `handoff-local-records`

_This is a deterministic compilation of every artifact the implementer needs. Read top to bottom._

## 1. Execution target

- **Node id:** `M3.2`
- **Title:** handoff status reports review records without a claim
- **Codename:** `handoff-local-records`
- **Type:** task
- **Status (own):** Not Started
- **Status (rollup):** Not Started
- **Execution (milestone hint):** Agentic-led
- **Touch zones:** specy_road/bundled_scripts/review_cli.py, specy_road/review_target.py, docs/orchestration.md, tests/

### Goal

A repository that never pushes claims can see the state of its review records and is never told to run a pushing command.

### Acceptance criteria

- **A1:** handoff status on a leaf with records under work/reviews/<ID>/ but no claim reports those records and their verdicts instead of calling them leftover
- **A2:** The hint names `--ref <branch>` and `do-next-available-task --local`, never the pushing pickup
- **A3:** docs/orchestration.md states that records are read from the working tree, are untracked by design, that policy comes from the integration branch, and that approvals persist as Reviewed-by trailers

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

### This node's planning sheet: `planning/M3.2_handoff-local-records_b06d628f-8f02-49c0-9366-7f9beee7ce20.md`

## Intent

A repository that never pushes claims can see the state of its review records and is never told to run a pushing command.

## Approach

The 'unclaimed' branch in review_cli treats every claimless leaf as having leftover files. Distinguish 'no records' from 'records present, no claim': the second lists the records (reuse the status renderer with --ref resolution) and hints at --local. The doc paragraph belongs under 'Hand-off files'.

## Tasks / checklist

- [ ] Split the unclaimed case in `_status_or_error`
- [ ] Reuse `_node_status` with an explicit ref when records exist
- [ ] One doc paragraph on where records are read from
- [ ] Tests for both unclaimed shapes

## References

- `docs/design-notes/v0-3-1-rc1-adopter-feedback-triage.md`
- `docs/orchestration.md`

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

The PM listed these touch zones: `specy_road/bundled_scripts/review_cli.py`, `specy_road/review_target.py`, `docs/orchestration.md`, `tests/`.

**TODO (DEV agent):** confirm these touch zones are accurate by scanning the codebase. Add or remove zones as appropriate, then report the final list in your implementation summary.

## 8. Rollup semantics (reference)

- Ancestor `rollup_status` is computed from leaf descendants.
- A non-leaf is `Complete` only when every leaf descendant is `Complete`.
- Otherwise the ancestor inherits the most pressing non-complete status (`Blocked` > `In Progress` > `Not Started`).
- Pickup targets actionable leaves; ancestors are context-only.

## 9. History (derived from git)

**Planning sheet**: revised in 1 commit; most recent `db6ae4f3`.
