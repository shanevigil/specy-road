# Optional AI tooling patterns (moved)

The material that was here now lives with the topic it belongs to. This pointer is removed in the release after 0.3.1.

- `specyrd init`, the skills it installs and what `--force` may touch → [install-and-usage.md: Skills](install-and-usage.md#skills-specyrd-init)
- `AGENTS.md`, `.specyrd/AGENTS.md`, the team and local addenda, and the `CLAUDE.md` imports → [install-and-usage.md: Agent rules](install-and-usage.md#agent-rules-agentsmd-and-specyrd)
- the shared-checkout guard hook for Claude Code, Codex and Cursor → [orchestration.md: Wiring the guard into a harness](orchestration.md#wiring-the-guard-into-a-harness)
- the prompt-submit hook that records a human's intervention → [orchestration-workers.md: The intervention hook](orchestration-workers.md#the-intervention-hook)
- worktrees and touch zones for parallel agents → [git-workflow.md](git-workflow.md)

specy-road ships no MCP server; agents reach it through the skills and the CLI. Entry files, IDE rule files, an application's own `docs/` and its CI gates are yours to design: nothing in them is part of specy-road's contract, and tracked docs win over any harness memory or rule.
