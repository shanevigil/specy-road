# Work-packet brief: `M3.9` — Worker and session CLI: resume permissions, roster provenance, event gaps `worker-cli-fixes`

_This is a deterministic compilation of every artifact the implementer needs. Read top to bottom._

## 1. Execution target

- **Node id:** `M3.9`
- **Title:** Worker and session CLI: resume permissions, roster provenance, event gaps
- **Codename:** `worker-cli-fixes`
- **Type:** task
- **Status (own):** Not Started
- **Status (rollup):** Not Started
- **Execution (milestone hint):** Agentic-led
- **Touch zones:** specy_road/worker_adapters.py, specy_road/worker_ops.py, specy_road/orchestrate_plan.py, specy_road/orchestration_pinned.py, specy_road/bundled_scripts/session_cli.py, specy_road/bundled_scripts/validate_roadmap.py, docs/orchestration-workers.md, docs/orchestration.md, tests/

### Goal

A custom worker command keeps its permissions across resumes, the plan says where its roster came from, and lost events are reported.

### Acceptance criteria

- **A1:** A roster channels.cli can name `{session_flag}` which expands to `--session-id <id>` on launch and `--resume <id>` on resume for claude-code, so one command serves both, and docs/orchestration-workers.md documents it and the harness settings-file route
- **A2:** orchestrate plan prints the ref the roster was read from, and when the local roadmap/orchestration.yaml is absent there or differs it says so instead of the may_process hint; validate warns the same way
- **A3:** worker sync reports a gap in event sequence numbers
- **A4:** session start --path accepts several values
- **A5:** In a nested layout the executor prompt and brief name the project root and give the implementation summary and hand-off paths relative to the worker's working directory, so a worker never writes them at the git root

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

### This node's planning sheet: `planning/M3.9_worker-cli-fixes_4785eb3e-6445-4f0f-9147-925ae859db43.md`

## Intent

A custom worker command keeps its permissions across resumes, the plan says where its roster came from, and lost events are reported.

## Approach

substitute_prompt owns placeholders; add the new one with the same whole-word rule. orchestrate_plan's _pick_executor message is replaced by a roster-source line computed once from pinned_config. Event seq gaps are visible in the events file reader.

## Tasks / checklist

- [ ] {session_flag} placeholder + docs
- [ ] roster-source message + validate warning
- [ ] sync gap report
- [ ] --path nargs
- [ ] Tests
- [ ] nested-layout paths in the executor prompt and brief

## References

- `docs/design-notes/v0-3-1-rc1-adopter-feedback-triage.md`
- `docs/orchestration-workers.md`
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

The PM listed these touch zones: `specy_road/worker_adapters.py`, `specy_road/worker_ops.py`, `specy_road/orchestrate_plan.py`, `specy_road/orchestration_pinned.py`, `specy_road/bundled_scripts/session_cli.py`, `specy_road/bundled_scripts/validate_roadmap.py`, `docs/orchestration-workers.md`, `docs/orchestration.md`, `tests/`.

**TODO (DEV agent):** confirm these touch zones are accurate by scanning the codebase. Add or remove zones as appropriate, then report the final list in your implementation summary.

## 8. Rollup semantics (reference)

- Ancestor `rollup_status` is computed from leaf descendants.
- A non-leaf is `Complete` only when every leaf descendant is `Complete`.
- Otherwise the ancestor inherits the most pressing non-complete status (`Blocked` > `In Progress` > `Not Started`).
- Pickup targets actionable leaves; ancestors are context-only.

## 9. History (derived from git)

**Planning sheet**: revised in 2 commits; most recent `db6ae4f3`, `7d3c5c51`.
