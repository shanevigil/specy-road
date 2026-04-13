# Structured planning (`planning/*.md`)

**Vision, phase, milestone, and task** nodes must set **`planning_dir`** to a repo-relative path to **one** feature sheet: `planning/<id>_<codename_slug>_<node_key>.md`.

Use `specy-road scaffold-planning <NODE_ID>` to create the file from the package template and set `planning_dir` on the node.

Each sheet should include YAML frontmatter with `node_id` and `node_key` matching the roadmap node. Validation enforces the filename pattern and frontmatter.

When implementing a task, read **ancestor** planning sheets (parent milestone and phase) for context, then the node’s own sheet.
