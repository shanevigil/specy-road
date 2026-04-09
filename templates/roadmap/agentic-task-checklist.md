# Checklist: implementable `[agentic]` sub-tasks

Use for authoring and review. Every `[agentic]` item should satisfy all items below.

## Required (five elements)

- [ ] **Artifact + action** — Named entity (handler, component, record), not “implement X”.
- [ ] **Contract / ADR citation** — Document + section or entity; traceable to a path under `shared/`, `docs/`, `specs/`, or `adr/`.
- [ ] **Interface contract** — Inputs → outputs (API, DB shape, props).
- [ ] **Constraints** — Security, logging, performance, UX bindings.
- [ ] **Dependency** — Prior sub-task id, merged milestone, or stub flag.

## Recommended

- [ ] **Success signal** — Observable behavior or test that proves done.
- [ ] **Forbidden patterns** — One line of what not to do (e.g. “no real LLM calls — stub only”).

## Stack-agnostic language

- [ ] No framework, cloud vendor, or SDK names in the roadmap line (those belong in ADRs and feature specs).
- [ ] Describes *what* and *which contract*, not *which tool*.

## Ordering

- [ ] `[human-gate]` items that block coding appear **before** dependent `[agentic]` items.
- [ ] Mixed human + agent work is **split** into separate sub-tasks.
