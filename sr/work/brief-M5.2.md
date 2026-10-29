# Work-packet brief: `M5.2` — validate flags specy-road commands that do not exist in the consumer's agent files `stale-command-check`

_This is a deterministic compilation of every artifact the implementer needs. Read top to bottom._

## 1. Execution target

- **Node id:** `M5.2`
- **Title:** validate flags specy-road commands that do not exist in the consumer's agent files
- **Codename:** `stale-command-check`
- **Type:** task
- **Status (own):** Not Started
- **Status (rollup):** Not Started
- **Execution (milestone hint):** Agentic-led
- **Touch zones:** specy_road/bundled_scripts/validate_roadmap.py, specy_road/cli.py, specy_road/managed_block.py, tests/

### Goal

A consumer's own AGENTS.md or CLAUDE.md never sends agents to a specy-road command that no longer exists.

### Acceptance criteria

- **A1:** validate warns for each `specy-road <subcommand>` or `specyrd <subcommand>` mentioned in AGENTS.md or CLAUDE.md (outside managed blocks) whose subcommand is not registered
- **A2:** Known aliases and deprecated names are listed with their replacement
- **A3:** The check never fails validation and has no false positive on the toolkit's own docs

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

### This node's planning sheet: `planning/M5.2_stale-command-check_e94029df-277a-47a3-a4fb-16036d6c9d0e.md`

## Intent

A consumer's own AGENTS.md or CLAUDE.md never sends agents to a specy-road command that no longer exists.

## Approach

The command set is `_known_commands` in cli.py; scan the two files with a regex for `specy-road <word>` and skip the managed block via managed_block._split.

## Tasks / checklist

- [ ] Scanner + warning
- [ ] Alias table
- [ ] Tests on fixtures

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

The PM listed these touch zones: `specy_road/bundled_scripts/validate_roadmap.py`, `specy_road/cli.py`, `specy_road/managed_block.py`, `tests/`.

**TODO (DEV agent):** confirm these touch zones are accurate by scanning the codebase. Add or remove zones as appropriate, then report the final list in your implementation summary.

## 8. Rollup semantics (reference)

- Ancestor `rollup_status` is computed from leaf descendants.
- A non-leaf is `Complete` only when every leaf descendant is `Complete`.
- Otherwise the ancestor inherits the most pressing non-complete status (`Blocked` > `In Progress` > `Not Started`).
- Pickup targets actionable leaves; ancestors are context-only.

## 9. History (derived from git)

**Planning sheet**: revised in 1 commit; most recent `db6ae4f3`.
