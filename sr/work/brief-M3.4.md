# Work-packet brief: `M3.4` — Brainstorm prompts: shards from the allocation, per-pass files, framing with proposed answers `brainstorm-prompt-fixes`

_This is a deterministic compilation of every artifact the implementer needs. Read top to bottom._

## 1. Execution target

- **Node id:** `M3.4`
- **Title:** Brainstorm prompts: shards from the allocation, per-pass files, framing with proposed answers
- **Codename:** `brainstorm-prompt-fixes`
- **Type:** task
- **Status (own):** Not Started
- **Status (rollup):** Not Started
- **Execution (milestone hint):** Agentic-led
- **Touch zones:** specy_road/bundled_scripts/brainstorm_prompt.py, specy_road/bundled_scripts/brainstorm_prompt_diverge.py, specy_road/bundled_scripts/brainstorm_prompt_evidence.py, specy_road/bundled_scripts/brainstorm_cli.py, specy_road/bundled_scripts/brainstorm_cli_args.py, specy_road/bundled_scripts/brainstorm_cli_v2.py, specy_road/bundled_scripts/brainstorm_cli_args_v2.py, specy_road/bundled_scripts/brainstorm_session.py, specy_road/templates/specyrd/commands/specyrd-brainstorm.md, specy_road/templates/specyrd/agents-md-block.md, docs/brainstorming.md, tests/

### Goal

A brainstorm run by an agent starts without anchoring on the roadmap, frames the question without a cold questionnaire, and keeps every pass's prompt for audit.

### Acceptance criteria

- **A1:** The specyrd-brainstorm skill and the managed AGENTS.md block say to run `brainstorm start` before reading the digest or roadmap
- **A2:** The round-1 prompt tells the agent to propose an answer per framing question from what the PM already said, mark answered ones 'assumed', and lists the canonical frame keys (including deadline and budget), with outcome, served, not-the-question and assumed-vs-known marked required
- **A3:** `--panel N` shard cells are derived from the recorded allocation when one exists, and shard prompts carry the recorded frame
- **A4:** Each pass writes its own prompt file (-r1-, -r2-, -recommend-, -evidence-) and nothing overwrites an earlier pass's prompt
- **A5:** Prompts omit the 'roadmap-context.md (missing)' line when the file is absent
- **A6:** `brainstorm start` warns when run on the integration branch and suggests chore/brainstorm-<slug>
- **A7:** Every command prints the next step in order (round -> recommend -> evidence/verify -> triage -> promote)

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

### This node's planning sheet: `planning/M3.4_brainstorm-prompt-fixes_07daa56a-7dff-4444-9b72-f2bf7cde7451.md`

## Intent

A brainstorm run by an agent starts without anchoring on the roadmap, frames the question without a cold questionnaire, and keeps every pass's prompt for audit.

## Approach

All prompt text lives in brainstorm_prompt*.py; shard cells come from shard_lines(), which indexes OPERATORS/DIRECTIONS by shard number. Read the allocation text recorded by `frame --allocation` (free text today: parse 'sN' cells when present, else fall back). Per-pass file names change session_path helpers only. Keep the managed block within its line budget (one clause).

## Tasks / checklist

- [ ] Skill + block clause: start before reading
- [ ] Framing section rewrite with proposed answers and canonical keys
- [ ] Shard cells from the allocation; frame lines in shard prompts
- [ ] Per-pass prompt file names
- [ ] Drop the (missing) line; integration-branch warning at start; next-step hints
- [ ] Tests for each

## References

- `docs/design-notes/v0-3-1-rc1-adopter-feedback-triage.md`
- `docs/brainstorming.md`
- `docs/design-notes/v0-3-1-brainstorm-v2.md`

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

The PM listed these touch zones: `specy_road/bundled_scripts/brainstorm_prompt.py`, `specy_road/bundled_scripts/brainstorm_prompt_diverge.py`, `specy_road/bundled_scripts/brainstorm_prompt_evidence.py`, `specy_road/bundled_scripts/brainstorm_cli.py`, `specy_road/bundled_scripts/brainstorm_cli_args.py`, `specy_road/bundled_scripts/brainstorm_cli_v2.py`, `specy_road/bundled_scripts/brainstorm_cli_args_v2.py`, `specy_road/bundled_scripts/brainstorm_session.py`, `specy_road/templates/specyrd/commands/specyrd-brainstorm.md`, `specy_road/templates/specyrd/agents-md-block.md`, `docs/brainstorming.md`, `tests/`.

**TODO (DEV agent):** confirm these touch zones are accurate by scanning the codebase. Add or remove zones as appropriate, then report the final list in your implementation summary.

## 8. Rollup semantics (reference)

- Ancestor `rollup_status` is computed from leaf descendants.
- A non-leaf is `Complete` only when every leaf descendant is `Complete`.
- Otherwise the ancestor inherits the most pressing non-complete status (`Blocked` > `In Progress` > `Not Started`).
- Pickup targets actionable leaves; ancestors are context-only.

## 9. History (derived from git)

**Planning sheet**: revised in 1 commit; most recent `db6ae4f3`.
