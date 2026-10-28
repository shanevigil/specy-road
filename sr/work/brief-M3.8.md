# Work-packet brief: `M3.8` — Upgrade and validate report drift and migrations plainly `upgrade-and-validate-checks`

_This is a deterministic compilation of every artifact the implementer needs. Read top to bottom._

## 1. Execution target

- **Node id:** `M3.8`
- **Title:** Upgrade and validate report drift and migrations plainly
- **Codename:** `upgrade-and-validate-checks`
- **Type:** task
- **Status (own):** Not Started
- **Status (rollup):** Not Started
- **Execution (milestone hint):** Agentic-led
- **Touch zones:** specy_road/bundled_scripts/refresh_stubs.py, specy_road/bundled_scripts/upgrade.py, specy_road/agents_md_block.py, specy_road/bundled_scripts/validate_roadmap.py, specy_road/bundled_scripts/roadmap_edit_fields.py, docs/install-and-usage.md, tests/

### Goal

An adopter can tell a deliberate upgrade from an accidental one and is not sent to files they do not have.

### Acceptance criteria

- **A1:** validate warns once when the running version differs from a pin declared in .specyrd/manifest.json or requirements*.txt
- **A2:** The AGENTS.md section warning says the section differs from what this version writes, not 'from another version'
- **A3:** `upgrade` copies shipped docs the load order names (docs/supply-chain-security.md) when missing, and validate warns on a load-order path that does not exist
- **A4:** `refresh-stubs --dry-run` prints a one-line migration summary (N command stubs become skills)
- **A5:** edit-node warns when a list field receives a value that looks like a JSON list
- **A6:** The parent-status warning fires only when a stored Complete disagrees with a non-Complete rollup or vice versa; an In Progress parent with a Not Started rollup is not told to downgrade
- **A7:** `specy-road version` is an alias of `--version`, and an unknown command exits non-zero

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

### This node's planning sheet: `planning/M3.8_upgrade-and-validate-checks_9834a43e-0495-4d25-ba3e-d41d54d22e0d.md`

## Intent

An adopter can tell a deliberate upgrade from an accidental one and is not sent to files they do not have.

## Approach

Small additions at existing seams: a `pinned_version()` reader (manifest `pin`, else requirements lines matching specy-road==), the warning text in agents_md_block, a copy-missing step in upgrade next to refresh-profiles, the migration count in _report, and a shape check in _nonempty_lines callers.

## Tasks / checklist

- [ ] pin warning
- [ ] wording
- [ ] shipped-doc copy + load-order check
- [ ] dry-run summary
- [ ] JSON-looking value warning
- [ ] Tests
- [ ] parent-status warning scope
- [ ] version alias + unknown-command exit

## References

- `docs/design-notes/v0-3-1-rc1-adopter-feedback-triage.md`
- `docs/install-and-usage.md`

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

The PM listed these touch zones: `specy_road/bundled_scripts/refresh_stubs.py`, `specy_road/bundled_scripts/upgrade.py`, `specy_road/agents_md_block.py`, `specy_road/bundled_scripts/validate_roadmap.py`, `specy_road/bundled_scripts/roadmap_edit_fields.py`, `docs/install-and-usage.md`, `tests/`.

**TODO (DEV agent):** confirm these touch zones are accurate by scanning the codebase. Add or remove zones as appropriate, then report the final list in your implementation summary.

## 8. Rollup semantics (reference)

- Ancestor `rollup_status` is computed from leaf descendants.
- A non-leaf is `Complete` only when every leaf descendant is `Complete`.
- Otherwise the ancestor inherits the most pressing non-complete status (`Blocked` > `In Progress` > `Not Started`).
- Pickup targets actionable leaves; ancestors are context-only.

## 9. History (derived from git)

**Planning sheet**: revised in 2 commits; most recent `db6ae4f3`, `c5db7c3e`.
