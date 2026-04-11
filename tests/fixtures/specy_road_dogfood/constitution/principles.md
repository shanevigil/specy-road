# Principles

These are judgment heuristics—not automated pass/fail rules. Enforceable caps live in [`../constraints/`](../constraints/).

- **Roadmap-first:** Agents derive work from roadmap items; **phase and milestone** nodes must point to `planning/<node-id>/` via `planning_dir` — that is where feature **overview / plan / tasks** narrative lives (validated Markdown), while the graph stays in `roadmap/` JSON.
- **Adaptive planning:** Sub-task (`task`) nodes may rely on parent milestone planning or add `tasks/*.md` under the owner’s `planning_dir`; keep narrative out of chat and in the repo.
- **Separation of concerns:** Do not embed operational rules (file size, tool choice) in purpose or principles; put them in **constraints** and **shared** contracts.
- **Multi-agent safety:** Use codenames, touch zones, and a registry so parallel work is visible before conflicts occur.
- **Immutable roadmap IDs:** Never renumber; gaps are allowed when items are removed.
- **Hierarchical roadmap chunks:** Split the graph across logically organized files under [`roadmap/`](../roadmap/): a JSON **manifest** (`manifest.json`) lists ordered chunk paths; **JSON** chunks (`{"nodes": [...]}` or equivalent shapes) hold node definitions. Keep each file readable and git-diff-friendly. No chunk should exceed **~500 lines** unless that file holds **exactly one** node (smallest grain), e.g. a very long checklist — enforceable via validation. Thresholds are configurable in [`../constraints/file-limits.yaml`](../constraints/file-limits.yaml) (`roadmap_json_chunk_max_lines`, `roadmap_manifest_max_lines`).
- **Stack-agnostic roadmaps:** Roadmap tasks describe *what* and *which contract*; stack choices belong in ADRs and feature specs under [`../shared/`](../shared/).
