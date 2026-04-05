# Principles

These are judgment heuristics—not automated pass/fail rules. Enforceable caps live in [`../constraints/`](../constraints/).

- **Roadmap-first:** Agents derive work from roadmap items; optional structured planning (`specify/<node-id>/`) exists for complex work only.
- **Adaptive planning:** Default is lightweight in-session planning; structured spec → plan → tasks when risk or compliance demands it.
- **Separation of concerns:** Do not embed operational rules (file size, tool choice) in purpose or principles; put them in **constraints** and **shared** contracts.
- **Multi-agent safety:** Use codenames, touch zones, and a registry so parallel work is visible before conflicts occur.
- **Immutable roadmap IDs:** Never renumber; gaps are allowed when items are removed.
- **Hierarchical roadmap YAML:** Split the graph across logically organized files under [`roadmap/`](../roadmap/) (manifest + chunks); keep each file readable. No chunk should exceed **400 lines** unless that file holds **exactly one** task/sub-task node (smallest grain), e.g. a very long checklist—enforceable via validation.
- **Stack-agnostic roadmaps:** Roadmap tasks describe *what* and *which contract*; stack choices belong in ADRs and feature specs under [`../shared/`](../shared/).
