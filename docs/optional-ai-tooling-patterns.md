# Optional AI tooling patterns

**This document is not part of specy-road’s core contract.** It collects patterns some teams use when layering **coding agents** (Claude Code, Cursor, Copilot, etc.) on top of a product repository. You may adopt none, some, or all of them.

For coordination **inside** this kit, prefer [`roadmap/registry.yaml`](../roadmap/registry.yaml) and [`git-workflow.md`](git-workflow.md). Some application repos use a markdown table such as `docs/roadmap-status.md` instead—that is a **team convention**, not what this repository uses by default.

---

## Core idea: documentation as source of truth

Treat durable rules, architecture decisions, and conventions as **version-controlled artifacts** agents can read. Chat and comments are not substitutes for files when a rule must hold across sessions.

Principles that age well:

1. **Docs over verbal agreements** — If it matters, it lives where an agent (or a new teammate) can find it.
2. **Design for careful readers** — Be explicit; ambiguity becomes wrong assumptions.
3. **Multi-agent coordination is structural** — Codenames, touch zones, and registration reduce collisions (see [`git-workflow.md`](git-workflow.md)).
4. **Small, cohesive files** — Easier to load fully and reason about; align with [`constraints/file-limits.yaml`](../constraints/file-limits.yaml) in *this* repo, or define your own limits in *your* product repo.
5. **Enforce what must stick** — “Guidelines” that are never checked drift; put must-hold rules in CI or validators where possible.

---

## Optional “five layers” (product repos)

Many teams combine:

| Layer | Typical location | Role |
| ----- | ---------------- | ---- |
| Entry point | `CLAUDE.md` or vendor equivalent | Dense project contract (stack, structure, pointers) |
| IDE rules | `.cursor/rules/*.mdc` or similar | Scoped rules by path or always-on |
| Specifications | `docs/*.md` | Architecture, API, commands, hosting |
| Session memory | Vendor-specific store | High-signal, lean notes (avoid duplicating repo docs) |
| Verification | CI, scripts, compose | Pass/fail gates |

When layers conflict, **tracked docs in the repo** should win.

---

## Optional: `CLAUDE.md` or equivalent entry file

If your tool reads a root entry file, keep it **short** and link out to `docs/`. Useful sections: project identity, tech stack with versions, directory map, workflow pointers, and a table of canonical docs.

For **roadmap-driven branches** and registration, point to your git workflow doc. In **this** repository that is [`git-workflow.md`](git-workflow.md) and **`roadmap/registry.yaml`** — not a free-form status file unless your team chose one.

---

## Optional: Cursor (or IDE) rules

Rule files can scope instructions by glob (e.g. backend vs frontend). Prefer **pointers** to canonical docs over pasting large policies in every rule. Keep “do not refactor unrelated code”-style scope rules if your team needs them.

---

## Optional: `docs/` in an application repository

Typical high-value docs for app repos:

- **Architecture** — Layering, imports, errors, configuration access.
- **API or contract** — Schemas, endpoints, type mapping if you have a split stack.
- **Commands** — Exact dev, test, and lint commands (including PATH quirks).
- **Git workflow** — Branch naming, merge policy, **registration** and touch zones.

specy-road already separates **roadmap graph** (`roadmap.yaml`) from **active claims** (`registry.yaml`). Markdown roadmaps or `docs/roadmap-status.md` are optional patterns for repos that do not use this kit’s YAML registry.

---

## Optional: verification gates

Many teams define a small set of **mandatory** checks before merge (e.g. typecheck + lint, tests, container build). Tune gates for speed and clarity; document them so agents and humans run the same commands. This kit validates the roadmap with `scripts/validate_roadmap.py`; your **application** may add language-specific gates.

---

## Optional: MCP servers

[Model Context Protocol](https://modelcontextprotocol.io/) servers expose structured tools (git, Docker, issue trackers) instead of ad hoc shell. Useful when your workflow benefits from scoped, typed actions—not required for specy-road.

---

## Optional: git worktrees for parallel agents

Separate worktrees give isolated working trees while sharing history. Pair with **non-overlapping touch zones** and registration so two agents do not edit the same paths blindly. See [`git-workflow.md`](git-workflow.md) for this repo’s protocol.

---

## Optional: prompt habits

- **Atomic tasks** — One clear scope per request; mirrors roadmap discipline.
- **Curated context** — Prefer briefs and cited docs over pasting entire trees.
- **Tests as guardrails** — Test or contract sketches before large implementations often reduce rework (especially for generated code).

---

## Checklists (adapt to your repo)

**New roadmap-driven work (specy-road style):**

- Confirm gates and dependencies for the milestone.
- Read `roadmap/registry.yaml` for overlapping touch zones.
- Branch `feature/rm-<codename>`; first commit registers work per [`git-workflow.md`](git-workflow.md).
- Implement; remove registry entry before merge.

**Greenfield product repo (optional, if you use markdown status):**

- Some teams maintain `docs/roadmap-status.md` and register there first commit instead of YAML—equivalent **discipline**, different storage. Prefer **one** system per repo.

---

## See also

- [`philosophy-and-scope.md`](philosophy-and-scope.md) — what specy-road requires vs leaves open
- [`architecture.md`](architecture.md) — validation and brief generation in this repository
- [`git-workflow.md`](git-workflow.md) — branches, registry, merge-back
