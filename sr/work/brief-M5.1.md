# Work-packet brief: `M5.1` — Every managed AGENTS.md rule carries its provenance in the template `rule-provenance`

_This is a deterministic compilation of every artifact the implementer needs. Read top to bottom._

## 1. Execution target

- **Node id:** `M5.1`
- **Title:** Every managed AGENTS.md rule carries its provenance in the template
- **Codename:** `rule-provenance`
- **Type:** task
- **Status (own):** Not Started
- **Status (rollup):** Not Started
- **Execution (milestone hint):** Agentic-led
- **Touch zones:** specy_road/templates/specyrd/agents-md-block.md, specy_road/templates/specyrd/claude-md-block.md, specy_road/agents_md_block.py, specy_road/agent_guide_block.py, tests/

### Goal

Each rule the toolkit ships can name the failure it prevents, without costing consumers a byte of context.

### Acceptance criteria

- **A1:** Every rule bullet in the managed AGENTS.md and CLAUDE.md templates is followed by an HTML comment naming the failure it prevents, where it is enforced, and a reference
- **A2:** The renderer strips those comments, so rendered sections are byte-identical to today's apart from intended text
- **A3:** A test fails when a rule bullet has no provenance comment

## 2. Ancestor context chain

- **M5** (phase) — Agent context and outcomes _(rollup: Not Started)_

## 3. Planning context (inlined)

### Ancestor planning sheet: `planning/M5_context-and-outcomes_0e8ca94e-4046-47b3-ab39-50e2c9bad986.md`

## Intent

The research-backed additions chosen from the PM-role and agent-context studies: rules that carry their provenance, measurable always-injected context, a stale-command check, and an outcome record that closes the loop from shipped to learned.

## Approach

Leaves under this phase are picked by agents through the task loop; each leaf's sheet cites the triage note row it closes.

## Tasks / checklist

- [ ] Every leaf Complete through the review gate

## References

- `docs/design-notes/v0-3-1-rc1-adopter-feedback-triage.md`

### This node's planning sheet: `planning/M5.1_rule-provenance_40829e1f-f1d9-4368-a53f-ee8f27cd2566.md`

## Intent

Each rule the toolkit ships can name the failure it prevents, without costing consumers a byte of context.

## Approach

Format: `<!-- prevents: ... | enforced: ... | ref: ... -->` after each bullet. Strip in render_agents_lines and the guide renderer with one shared helper.

## Tasks / checklist

- [ ] Provenance comments on every rule
- [ ] Shared stripping helper
- [ ] Test

## References

- `docs/design-notes/agent-guidance-and-shared-checkouts.md`

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

The PM listed these touch zones: `specy_road/templates/specyrd/agents-md-block.md`, `specy_road/templates/specyrd/claude-md-block.md`, `specy_road/agents_md_block.py`, `specy_road/agent_guide_block.py`, `tests/`.

**TODO (DEV agent):** confirm these touch zones are accurate by scanning the codebase. Add or remove zones as appropriate, then report the final list in your implementation summary.

## 8. Rollup semantics (reference)

- Ancestor `rollup_status` is computed from leaf descendants.
- A non-leaf is `Complete` only when every leaf descendant is `Complete`.
- Otherwise the ancestor inherits the most pressing non-complete status (`Blocked` > `In Progress` > `Not Started`).
- Pickup targets actionable leaves; ancestors are context-only.

## 9. History (derived from git)

**Planning sheet**: revised in 1 commit; most recent `db6ae4f3`.
