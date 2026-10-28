# Suggested prompts

Copy-paste prompts for adopting specy-road in an existing application
repository. They are kept in this repository (not shipped on PyPI) and each one
names the toolkit docs and templates it relies on, so they stay aligned with the
real formats. Run them in this order:

1. [`bootstrap-governance.md`](bootstrap-governance.md) — writes the governance
   artifacts (`vision.md`, `constitution/`, `constraints/`, `shared/`) from the
   project's existing docs, in specy-road's layout. Use first, after
   `specy-road init project`.
2. [`bootstrap-roadmap.md`](bootstrap-roadmap.md) — migrates roadmap-like notes
   into the merged JSON graph under `roadmap/`, the registry, and `planning/`
   feature sheets. Use once governance exists and `specy-road validate` runs.
3. [`bootstrap-agents-md.md`](bootstrap-agents-md.md) — produces or merges the
   repo's `AGENTS.md`, `CLAUDE.md`, and Cursor rules so agents read the roadmap
   first and respect the consumer/toolkit boundary. Use after the roadmap is in
   place, or whenever agent configuration drifts.
4. [`brainstorm-roadmap.md`](brainstorm-roadmap.md) — runs a diverge / converge
   / evidence brainstorm with `specy-road brainstorm` and promotes what survives
   into the graph. Use any time after the roadmap exists.

## Generic review, cleanup, security and audit passes

specy-road does not ship prompts for these. Your coding harness already has
built-in skills for code review, simplification, security review and similar
passes (for example Claude Code's review and security-review commands, or the
Cursor and Codex equivalents); use those. What specy-road owns is the
roadmap-specific review contract — `specy-road review-packet`,
`specy-road review record`, and the review gate — documented in
[`docs/orchestration.md`](../docs/orchestration.md).
