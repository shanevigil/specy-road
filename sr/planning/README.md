# Structured planning (`planning/*.md`)

**Vision, phase, milestone, task, and gate** nodes must set **`planning_dir`** to a repo-relative path to **one** Markdown sheet: `planning/<id>_<codename_slug>_<node_key>.md`.

Use `specy-road scaffold-planning <NODE_ID>` to create the file from the package template and set `planning_dir` on the node.

The **filename** encodes the display id, codename slug, and stable `node_key`; validation checks that pattern against the roadmap. The body is ordinary Markdown (no required YAML frontmatter). `specy-road scaffold-planning` picks the template by node **`type`**: for **`gate`**, **`## Why this gate exists` → `## Criteria to clear` → `## Decisions and notes` → `## Resolution` → `## References`** (PM hold documentation; same outline LLM Review targets for gates). For **vision, phase, milestone, and task**, **`## Intent` → `## Approach` → `## Tasks / checklist` → `## References`**. Do not repeat node id, `node_key`, or title in the body; those belong in the path and roadmap JSON.

When implementing a task, read **ancestor** planning sheets (parent milestone and phase) for context, then the node’s own sheet.
