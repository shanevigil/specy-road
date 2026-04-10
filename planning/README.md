# Structured planning (`planning/<node-id>/`)

**Phase and milestone** roadmap nodes **must** set **`planning_dir`** to a repo-relative directory (for example `planning/M1.1`). That folder is where the **feature narrative** lives: intent, plan, and task checklists in Markdown, alongside the canonical graph in `roadmap/` JSON.

Use templates from [`templates/planning-node/`](../templates/planning-node/) or scaffold from the CLI:

```text
planning/<node-id>/
  overview.md
  plan.md
  tasks.md   # optional; if present, YAML frontmatter must set node_id
```

Example: `planning/M1.1/` for milestone `M1.1`. Validation (`python scripts/validate_roadmap.py`) requires **`overview.md`** and **`plan.md`** for every `planning_dir`. **`tasks.md`** is optional; if present it must start with YAML frontmatter `node_id: <owner-node-id>`. Optional **`tasks/**/*.md`** per sub-task each need frontmatter `node_id: <that-task-id>` (must be the owner id or a descendant id). Orphan files under `planning/**/tasks/` without a matching `planning_dir` on any node fail validation.

**Ids:** Folder names and YAML `node_id` use the roadmap **display `id`** (e.g. `M1.1`). The graph’s `dependencies` field uses **`node_key` UUIDs** — see [Node fields reference](../docs/roadmap-authoring.md#display-id-vs-stable-node_key) in `docs/roadmap-authoring.md`.

## Relationship to the roadmap graph

- **`roadmap/`** — Canonical structure: IDs, status, dependencies, codenames, touch zones, and `planning_dir` pointer.
- **`planning/`** — Human-readable **overview → plan → tasks** for each phase/milestone; this is what agents and developers load for implementation context together with cited `shared/` contracts.

CLI: `specy-road scaffold-planning <NODE_ID>` creates the folder, templates, and sets `planning_dir`. Use `--task-id Mx.y.z` to add `tasks/Mx.y.z.md` under an existing `planning_dir`.
