# Optional structured planning (`planning/<node-id>/`)

Use **lightweight** planning by default (roadmap node + contracts + session notes in [`work/`](../work/)).

For cross-cutting or high-risk work, copy templates from [`templates/planning-node/`](../templates/planning-node/) into:

```text
planning/<node-id>/
  overview.md
  plan.md
  tasks.md
```

Example: `planning/M1.1/` for milestone `M1.1`. This is **not** required by CI; it complements the roadmap, which remains canonical.

## Linking from the roadmap graph

Set optional **`planning_dir`** on a roadmap node to a repo-relative path (e.g. `planning/M1.1`). When `planning_dir` is set, `python scripts/validate_roadmap.py` requires **`overview.md`** and **`plan.md`** in that folder. Optional **`tasks.md`** must start with YAML frontmatter `node_id: <owner-node-id>`. Optional **`tasks/**/*.md`** per sub-task each need frontmatter `node_id: <that-task-id>` (must be the owner id or a descendant id). Orphan files under `planning/**/tasks/` without a matching `planning_dir` on any node fail validation.

CLI: `specy-road scaffold-planning <NODE_ID>` creates the folder, templates, and sets `planning_dir`. Use `--task-id Mx.y.z` to add `tasks/Mx.y.z.md` under an existing `planning_dir`.
