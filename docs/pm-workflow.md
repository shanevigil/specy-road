# PM workflow: producing and codifying roadmap decisions

This document is for the person **shaping** the roadmap — a product manager, director, or technical lead who decides what gets built and in what order. You produce the artifacts that developers and agents consume.

The complementary guide for developers is [dev-workflow.md](dev-workflow.md).

---

## Your role in the system

| You own | You hand off |
|---------|-------------|
| Roadmap YAML authoring | Agentic-led milestones (once contracts exist) |
| Human-led gate decisions | Execution — branch, implement, test |
| Shared contracts under `shared/` | Merge-back review (spot-check, not line-review) |
| Registry hygiene (active claims) | Day-to-day CI / validation failures |
| Export cadence (stakeholder views) | — |

You are not the first person to touch `scripts/` or `tests/` — those are dev territory. You are the last person to approve a milestone before it closes.

---

## Day-in-the-life: three modes

### 1. Planning (authoring nodes)

**When:** start of a phase, incoming requirement, new decision.

1. Read [`vision.md`](../vision.md) — ensure the change fits the project's invariants.
2. Open the relevant chunk file under `roadmap/phases/`. If the phase is new, add a chunk and wire it into [`roadmap/roadmap.yaml`](../roadmap/roadmap.yaml) via `includes`.
3. Add or update nodes. Full field reference: [roadmap-authoring.md — Node fields reference](roadmap-authoring.md#node-fields-reference).
4. Tag every sub-task with `execution_subtask`: `human`, `agentic`, or `human-gate`. See [Execution type tagging](roadmap-authoring.md#execution-type-tagging).
5. For `agentic` sub-tasks, fill in the five-field `agentic_checklist`. If you cannot fill all five fields — the spec is missing; write or stub it first.
6. Validate: `specy-road validate`. Fix any errors before committing.
7. Regenerate the markdown index: `specy-road export`.

**Commit message convention:** `chore(roadmap): <short description of what changed>`

### 2. Decision-making (human-gate tasks)

**When:** an `agentic` task has a blocking `human-gate` predecessor, or CI/review surfaces a judgment call.

1. Open the node with `execution_subtask: human-gate`.
2. Make the decision; record it in:
   - The `decision` block in the roadmap node (status, `decided_date`, `adr_ref`).
   - An ADR file under `docs/adr/` if the decision is architectural.
   - The relevant `shared/` contract if the decision changes an interface.
3. Update the sub-task `status` to `Complete`.
4. Validate and export.

A `human-gate` task blocks all `agentic` descendants — do not leave it `In Progress` indefinitely. If you need more time, add a `risks` note so developers know the hold is intentional.

### 3. Review (merge-back and registry hygiene)

**When:** a developer signals a roadmap-driven branch is ready to merge.

1. Check [`roadmap/registry.yaml`](../roadmap/registry.yaml) — the entry for that codename should be removed in the PR. If it is still present, request removal before merge.
2. Verify the milestone `status` in the chunk YAML is updated to `Complete` (or the agreed terminal state).
3. Confirm `specy-road validate` and `specy-road export --check` pass in CI.
4. Approve the merge. You do not need to review every line — trust the contracts and checklist.

---

## Authoring decisions: Human-led vs Agentic-led

**Rule of thumb:** if a step requires judgment, policy, stakeholder input, or cannot be verified by a machine — it is `human` or `human-gate`. If it can be fully described by a contract and a checklist — it is `agentic`.

| Situation | Tag |
|-----------|-----|
| Write an ADR or feature spec | `human` |
| Choose between two architecture options | `human-gate` (blocks downstream) |
| Implement per a complete spec | `agentic` |
| Acceptance / spot-check review | `human` |
| CI-verified code generation | `agentic` |

Set `execution_milestone` on the parent milestone to reflect the **dominant** work type (`Human-led`, `Agentic-led`, or `Mixed`).

See [Rules for authoring sub-tasks](roadmap-authoring.md#rules-for-authoring-sub-tasks) for the complete ruleset.

---

## Writing implementable contracts

Agents and developers consume contracts from `shared/`. Before marking a milestone `agentic`, ensure the cited contract exists and is complete enough to implement from.

A contract is implementable when it answers:
- **What entity or operation** is being produced.
- **What inputs and outputs** (schema, shape, fields).
- **What constraints** (security, compliance, performance).
- **What success looks like** (acceptance criteria or success signal).

If it cannot answer all four — the contract is a stub. Stubs are fine early, but mark the `agentic` task `Not Started` and add a `risks` note until the stub is filled in.

See [Spec crosswalk](roadmap-authoring.md#spec-crosswalk) for the types of contracts (feature spec, data model, API contract, etc.).

---

## Export cadence

Generate the markdown index after any structural YAML change:

```bash
specy-road export
```

Share [`roadmap.md`](../roadmap.md) with stakeholders — it is the canonical status table. The phase files under [`roadmap/phases/`](../roadmap/phases/) have goal, acceptance, and decision detail per milestone.

Do **not** hand-edit `roadmap.md` or phase markdown files — they are generated. Edit the YAML, then regenerate.

---

## Registry hygiene

[`roadmap/registry.yaml`](../roadmap/registry.yaml) tracks active work claims. As PM, you should:

- **Review it before kickoff meetings** — it shows who has claimed what and which touch zones are active.
- **Watch for stale entries** — an entry older than expected with no recent commits may indicate a blocked or abandoned branch. Follow up with the owner.
- **Flag overlapping touch zones** — `specy-road validate` emits warnings when two registry entries share nested paths. Surface this to the team before it becomes a merge conflict.

---

## Quick reference

```bash
specy-road validate          # validate roadmap YAML + registry
specy-road export            # regenerate roadmap.md and phase files
specy-road brief <NODE_ID>   # read what a dev/agent will receive for a node
```

Read the [roadmap authoring guide](roadmap-authoring.md) for full YAML field details, hierarchical chunk patterns, and line-count policy.
