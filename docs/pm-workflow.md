# PM workflow: producing and codifying roadmap decisions

This document is for the person **shaping** the roadmap — a product manager, director, or technical lead who decides what gets built and in what order. You produce the artifacts that developers and agents consume.

The complementary guide for developers is [dev-workflow.md](dev-workflow.md).

---

## Your role in the system

Agentic development compresses execution timescales dramatically. A single developer with agents can execute dozens of tasks per day; a team can run hundreds. Your job is not to approve each task — it is to **stay far enough ahead** that devs and agents are never blocked waiting for a contract, decision, or node to exist.

**Target horizon:** keep ready-to-execute `agentic` nodes available at a depth of roughly `(tasks per day per dev) × (number of devs)` ahead of current execution. If three devs each run ten tasks a day, the runway should be at least 30 nodes deep before the first one starts the morning.

| You own | You hand off entirely |
| --- | --- |
| Roadmap YAML authoring | All implementation |
| Human-led gate decisions (resolved in advance) | Branch, test, merge |
| Shared contracts under `shared/` | CI and validation failures |
| Maintaining the execution runway | Registry housekeeping during execution |
| Stakeholder views via export | Code review |

You do not review PRs. You do not approve merges. The contracts you write and the CI the team runs are the gates — not your sign-off on individual branches.

---

## Day-in-the-life: two modes

### 1. Runway maintenance (primary, ongoing)

Your main activity is keeping enough ready-to-execute nodes ahead of the team's execution pace.

**Signs the runway is too short:**

- Devs are waiting on a contract or decision before they can start a node
- Nodes marked `Not Started` with `agentic` execution but missing `agentic_checklist` fields
- `human-gate` tasks that haven't been resolved before devs reach them

**Batch authoring cadence (suggested):**

1. Check the current execution depth: open [`roadmap.md`](../roadmap.md) and count `Not Started` + `Agentic-led` nodes with no unresolved dependencies.
2. If the depth is below your target horizon, open the next chunk file and add nodes.
3. For each `agentic` sub-task, fill in all five `agentic_checklist` fields. If you cannot — the spec is missing; write or stub it first and add a `risks` note.
4. Resolve any `human-gate` tasks in the new batch before you stop. Do not leave `human-gate` nodes pending — they become blockers the moment a dev reaches them.
5. Validate: `specy-road validate`. Fix errors before committing.
6. Regenerate: `specy-road export`.

**Commit message convention:** `chore(roadmap): <short description of what changed>`

### 2. Decision-making (human-gate tasks)

**When:** a `human-gate` node exists in the upcoming execution horizon that has not been resolved.

Resolve these before devs reach them, not after:

1. Open the node with `execution_subtask: human-gate`.
2. Make the decision; record it in:
   - The `decision` block in the roadmap node (status, `decided_date`, `adr_ref`).
   - An ADR file under `docs/adr/` if the decision is architectural.
   - The relevant `shared/` contract if the decision changes an interface.
3. Update the sub-task `status` to `Complete`.
4. Validate and export.

A `human-gate` task left unresolved is a hold on every downstream `agentic` node. Treat resolving them as part of runway maintenance, not a reactive step.

---

## Monitoring execution (not approving it)

You observe progress through `roadmap.md` and the registry — not through PRs.

**Registry (`roadmap/registry.yaml`):**

- Shows who has claimed what and which touch zones are active
- A stale entry (claimed long ago, no recent commits) may indicate a blocked branch — follow up with the dev
- `specy-road validate` warns on overlapping touch zones; surface this to the team if needed

**Export:**

```bash
specy-road export
```

Check [`roadmap.md`](../roadmap.md) to see status across milestones. Share it with stakeholders as the canonical view — the phase files under [`roadmap/phases/`](../roadmap/phases/) have goal, acceptance, and decision detail.

You do not need to check in on individual PRs. If CI is green and the contract was complete, the work is correct by construction.

---

## Authoring decisions: Human-led vs Agentic-led

**Rule of thumb:** if a step requires judgment, policy, stakeholder input, or cannot be verified by a machine — it is `human` or `human-gate`. If it can be fully described by a contract and a checklist — it is `agentic`.

| Situation | Tag |
| --- | --- |
| Write an ADR or feature spec | `human` |
| Choose between two architecture options | `human-gate` (resolve before devs reach it) |
| Implement per a complete spec | `agentic` |
| Acceptance spot-check (optional) | `human` |
| CI-verified code generation | `agentic` |

Set `execution_milestone` on the parent milestone to reflect the **dominant** work type (`Human-led`, `Agentic-led`, or `Mixed`).

See [Rules for authoring sub-tasks](roadmap-authoring.md#rules-for-authoring-sub-tasks) for the complete ruleset.

---

## Writing implementable contracts

Before marking a milestone ready, ensure the contract in `shared/` is complete enough to implement from without asking clarifying questions.

A contract is implementable when it answers:

- **What entity or operation** is being produced.
- **What inputs and outputs** (schema, shape, fields).
- **What constraints** (security, compliance, performance).
- **What success looks like** (acceptance criteria or success signal).

If it cannot answer all four — the contract is a stub. Mark the `agentic` task `Not Started` and add a `risks` note until the stub is filled in. An incomplete contract means the dev will stall or guess — both cost more than the time it takes you to finish the spec.

See [Spec crosswalk](roadmap-authoring.md#spec-crosswalk) for the types of contracts (feature spec, data model, API contract, etc.).

---

## Quick reference

```bash
specy-road validate          # validate roadmap YAML + registry
specy-road export            # regenerate roadmap.md and phase files
specy-road brief <NODE_ID>   # read exactly what a dev/agent will receive
```

Read the [roadmap authoring guide](roadmap-authoring.md) for full YAML field details, hierarchical chunk patterns, and line-count policy.
