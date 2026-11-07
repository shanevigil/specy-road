# Philosophy and scope

This document is for **humans and coding agents** adopting or working on specy-road. What specy-road governs, and what it is not, is stated once in [`constitution/purpose.md`](../constitution/purpose.md); this page lists what the kit is **opinionated** about and what it **does not** prescribe.

## What specy-road is opinionated about

- **Roadmap-first evolution** — The graph under `roadmap/` ([`manifest.json`](../specy_road/templates/project/roadmap/manifest.json) + ordered **JSON** chunk files) is canonical: immutable milestone IDs, dependencies, gates, codenames, and touch zones. Nodes with **`planning_dir`** point at a single feature sheet under [`planning/`](../specy_road/templates/project/planning/README.md).
- **Separation of concerns** — [`constitution/`](../specy_road/templates/project/constitution/purpose.md) holds purpose and principles (human judgment); [`constraints/`](../specy_road/templates/project/constraints/README.md) holds enforceable, checkable rules; [`shared/`](../specy_road/templates/project/shared/README.md) holds contracts that tasks **cite** instead of restating in chat.
- **Multi-agent safety** — [`roadmap/registry.yaml`](../specy_road/templates/project/roadmap/registry.yaml) plus touch zones and registration on the integration branch ([`git-workflow.md`](git-workflow.md)) make parallel work visible before conflicts.
- **Multi-agent execution** — workers run on a named harness (`claude-code`, `codex`, `cursor`, or your own command) with a named model chosen from the roster; one writer holds a session at a time, and what a harness cannot do is reported as unsupported, never emulated ([`orchestration-workers.md`](orchestration-workers.md)).
- **Separated roles and recorded review** — whoever implements a leaf does not approve it; reviews are files bound to the commit they read, counted by the review gate against [`roadmap/orchestration.yaml`](../specy_road/templates/project/roadmap/orchestration.yaml) ([`orchestration.md`](orchestration.md)).
- **Ideas are evidence-bearing records** — `brainstorm` keeps every idea with its origin, sources and the human's decision in a tracked session file ([`brainstorming.md`](brainstorming.md)).
- **No model calls in coordination, no daemon** — the coordination CLI leaves model and search calls to the harness and reaches it through one-shot commands, hooks and skills; the exceptions are listed in principles 4 and 5 of [`constitution/principles.md`](../constitution/principles.md).

## Where specy-road sits

Other tools also drive coding-agent CLIs as workers; specy-road does too, but what is its own is the **combination** of four commitments:

1. **The roadmap graph lives in the repo** — work is picked, briefed and finished against that graph, not against a task queue the orchestrator owns.
2. **Separated roles, with fresh-session reviewers from a distinct family** — `reviewers_distinct_families` counts approvals by vendor family, so two sessions of one family count once.
3. **Reviews are bound to a commit** — a review under `work/reviews/<NODE_ID>/` names the commit it read; any later commit makes it stale.
4. **Tracked files plus shell commands are the only surface** — claims, briefs, prompts, hand-offs and reviews are files in git, driven by one-shot `specy-road` commands.

## What specy-road does not prescribe

- **Which IDE, agent CLI or model** fills the coordinator, executor or reviewer role; the team chooses them in the roster, and model profiles are data it picks from.
- **How** an agent plans or implements inside a session; that stays with the user and their harness.
- **Product-specific stacks** — stack choices belong in your application's ADRs and `shared/` contracts, not in the kit's core rules.

Optional IDE rules, `CLAUDE.md` files or your own MCP servers are collected in [`optional-ai-tooling-patterns.md`](optional-ai-tooling-patterns.md); they are not part of specy-road's contract. Anything that defines roadmap truth, contracts or enforceable limits lives under `constitution/`, `constraints/`, `roadmap/` and `shared/` in your project and is driven by the `specy-road` CLI; `specyrd init` only installs thin skills that point at those commands.

For the agent load order, see [`AGENTS.md`](../AGENTS.md) (toolkit contributors) or the `AGENTS.md` that `specy-road init project` writes (consumer projects).
