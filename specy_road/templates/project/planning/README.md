# Structured planning (`planning/*.md`)

**Vision, phase, milestone, and task** nodes must set **`planning_dir`** to a repo-relative path to **one** feature sheet: `planning/<id>_<codename_slug>_<node_key>.md`.

Use `specy-road scaffold-planning <NODE_ID>` to create the file from the package template and set `planning_dir` on the node.

The **filename** encodes the display id, codename slug, and stable `node_key`; validation checks that pattern against the roadmap. The body is ordinary Markdown (no required YAML frontmatter). Prefer starting the file with `## Intent` — do not repeat node id, `node_key`, or title; those belong in the path and roadmap JSON.

When implementing a task, read **ancestor** planning sheets (parent milestone and phase) for context, then the node’s own sheet.
