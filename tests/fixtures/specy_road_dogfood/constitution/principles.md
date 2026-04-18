# Principles

These are judgment heuristics—not automated pass/fail rules. Enforceable caps live in [`../constraints/`](../constraints/).

- **Roadmap-first:** Agents derive work from roadmap items; nodes with **`planning_dir`** point to a single **`planning/<id>_<slug>_<node_key>.md`** feature sheet (validated Markdown), while the graph stays in `roadmap/` JSON.
- **Adaptive planning:** Read **ancestor** feature sheets (phase/milestone) for context when working on a task; keep narrative out of chat and in the repo.
- **Separation of concerns:** Do not embed operational rules (file size, tool choice) in purpose or principles; put them in **constraints** and **shared** contracts.
- **Multi-agent safety:** Use codenames, touch zones, and a registry so parallel work is visible before conflicts occur.
- **Stable node identity:** Each node’s **`node_key`** (UUID) never changes. Display **`id`** (`M0.1`, …) may be renumbered when the outline is reorganized; **`dependencies`** use **`node_key`**, not display ids. Gaps in numbering are allowed when items are removed.
- **Hierarchical roadmap chunks:** Split the graph across logically organized files under [`roadmap/`](../roadmap/): a JSON **manifest** (`manifest.json`) lists ordered chunk paths; **JSON** chunks (`{"nodes": [...]}` or equivalent shapes) hold node definitions. Keep each file readable and git-diff-friendly. No chunk should exceed **~500 lines** unless that file holds **exactly one** node (smallest grain), e.g. a very long checklist — enforceable via validation. Thresholds are configurable in [`../constraints/file-limits.yaml`](../constraints/file-limits.yaml) (`roadmap_json_chunk_max_lines`, `roadmap_manifest_max_lines`).
- **Stack-agnostic roadmaps:** Roadmap tasks describe *what* and *which contract*; stack choices belong in ADRs and feature specs under [`../shared/`](../shared/).
