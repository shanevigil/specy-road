# Structured planning (`planning/<node-id>/`)

**Phase and milestone** nodes must set **`planning_dir`** in the roadmap graph. Each folder holds **overview.md** and **plan.md** (required); optional **tasks.md** and **tasks/** subtasks with YAML frontmatter `node_id:`.

Use `specy-road scaffold-planning <NODE_ID>` to create or extend folders from templates.
