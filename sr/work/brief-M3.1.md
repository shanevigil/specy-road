# Work-packet brief: `M3.1` — Refuse to pick up leaves whose planning sheet is still a placeholder `unauthored-leaf-guard`

_This is a deterministic compilation of every artifact the implementer needs. Read top to bottom._

## 1. Execution target

- **Node id:** `M3.1`
- **Title:** Refuse to pick up leaves whose planning sheet is still a placeholder
- **Codename:** `unauthored-leaf-guard`
- **Type:** task
- **Status (own):** Not Started
- **Status (rollup):** Not Started
- **Execution (milestone hint):** Agentic-led
- **Touch zones:** specy_road/bundled_scripts/do_next_task_leaf_guards.py, specy_road/bundled_scripts/do_next_available.py, specy_road/bundled_scripts/session_plan.py, specy_road/bundled_scripts/planning_sheet_bootstrap.py, specy_road/bundled_scripts/brainstorm_promote.py, specy_road/bundled_scripts/brief_acceptance.py, specy_road/bundled_scripts/validate_roadmap.py, tests/

### Goal

An agent is never handed a leaf whose sheet still carries the scaffold or promote placeholder text and whose node has no acceptance criteria.

### Acceptance criteria

- **A1:** do-next-available-task skips a leaf whose sheet contains the scaffold-planning or promote placeholder text and whose node has no acceptance, and says why
- **A2:** grind-session --plan lists such leaves as not ready with the reason; --allow-unauthored overrides
- **A3:** validate prints one block naming every such open leaf (capped like the acceptance warning) and validate --all prints them all
- **A4:** A leaf whose sheet was filled in, or whose node has acceptance, is picked up as before

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

### This node's planning sheet: `planning/M3.1_unauthored-leaf-guard_2a9def0a-45e8-4fa5-8f06-02e426749f85.md`

## Intent

An agent is never handed a leaf whose sheet still carries the scaffold or promote placeholder text and whose node has no acceptance criteria.

## Approach

Both placeholder shapes are known strings the toolkit itself writes: scaffold-planning's section bodies (planning_sheet_bootstrap) and promote's 'Rewrite this section once the slice is properly scoped' line. Detect them with one helper that both the pickup guard and validate call; do not add a schema field. Keep the guard in the leaf-guard module next to the gate checks so grind-session and do-next share it.

## Tasks / checklist

- [ ] One `placeholder_sheet(root, node) -> str | None` helper returning the reason
- [ ] Pickup guard: skip with a printed reason; `--allow-unauthored` on do-next and grind-session
- [ ] validate block (shared cap) and `validate --all`
- [ ] Tests: scaffolded leaf refused, filled sheet accepted, promote-skeleton refused, --all lists everything

## References

- `docs/design-notes/v0-3-1-rc1-adopter-feedback-triage.md`
- `docs/roadmap-authoring.md`
- `docs/grind-session.md`

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

The PM listed these touch zones: `specy_road/bundled_scripts/do_next_task_leaf_guards.py`, `specy_road/bundled_scripts/do_next_available.py`, `specy_road/bundled_scripts/session_plan.py`, `specy_road/bundled_scripts/planning_sheet_bootstrap.py`, `specy_road/bundled_scripts/brainstorm_promote.py`, `specy_road/bundled_scripts/brief_acceptance.py`, `specy_road/bundled_scripts/validate_roadmap.py`, `tests/`.

**TODO (DEV agent):** confirm these touch zones are accurate by scanning the codebase. Add or remove zones as appropriate, then report the final list in your implementation summary.

## 8. Rollup semantics (reference)

- Ancestor `rollup_status` is computed from leaf descendants.
- A non-leaf is `Complete` only when every leaf descendant is `Complete`.
- Otherwise the ancestor inherits the most pressing non-complete status (`Blocked` > `In Progress` > `Not Started`).
- Pickup targets actionable leaves; ancestors are context-only.

## 9. History (derived from git)

**Planning sheet**: revised in 1 commit; most recent `db6ae4f3`.
