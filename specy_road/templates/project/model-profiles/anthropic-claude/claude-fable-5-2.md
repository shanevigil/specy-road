---
profile_schema: 2
family: Anthropic Claude
track: Fable
model: Claude Fable 5.2
api_id: claude-fable-5-2
aliases:
  - claude-fable-5-2-low
  - claude-fable-5-2-low-fast
  - claude-fable-5-2-medium
  - claude-fable-5-2-medium-fast
  - claude-fable-5-2-high
  - claude-fable-5-2-high-fast
  - claude-fable-5-2-xhigh
  - claude-fable-5-2-xhigh-fast
  - claude-fable-5-2-max
  - claude-fable-5-2-max-fast
checkpoint: unknown
alias_moves: unknown
version_rank: latest
release_date: unknown
researched: 2026-11-19
researcher: field
supersedes: claude-fable-5-1
access:
  context_tokens: 1000000
  output_tokens: unknown
  cli: CLAUDE_CODE_DISABLE_AUTO_MEMORY=1 CLAUDE_CODE_DISABLE_BACKGROUND_TASKS=1 claude -p "<prompt>"
  cli_verified_from: 'not run with this model; the claude-code executor template (harness-facts.yaml) with the api_id the Cursor inventory names [S1]'
  subagents: 'unknown No host source describes its delegation behaviour [S1]'
  effort_controls: 'levels low, medium, high, xhigh, max, each with a -fast variant, in Cursor''s ids; the inventory marks no Fable 5.2 id as default (only auto) and names no default effort [S1]'
  effort_map: { minimal: unknown, low: low, medium: medium, high: high, max: max }
  launch_mode: full   # bare (--bare) skips settings and installed-plugin hooks (not managed-plugin hooks), auto memory and CLAUDE.md auto-discovery, and authenticates only with ANTHROPIC_API_KEY or an apiKeyHelper (2.1.329 help)
cost_usd_per_mtok: { input: unknown, output: unknown, cached_input: unknown, fast_input: unknown, fast_output: unknown }
data_handling: 'Cursor''s display name for every Claude Fable 5.2 id ends "(NO ZDR)" [S1]. Retention, training use, residency and deployment options elsewhere were not researched for this model.'
role_fit:
  coordinator: { score: 3, reason: 'Not piloted as a coordinator; no evidence either way', sources: [] }
  executor:    { score: 3, reason: 'Not piloted as an executor; no evidence either way', sources: [] }
  reviewer:    { score: 3, reason: 'Not piloted as a reviewer; same anthropic family as the Opus and earlier Fable profiles, so it adds no family diversity to a review pair with them', sources: [] }
---
## Orchestration: harness features to avoid

When this model runs as a roster **executor** on `claude-code`, `worker delegate` exports in the process environment (via `harness_env`, not only `access.cli` / `specy-road prompt --channel cli`):

| Feature | Switch |
|---|---|
| auto memory (shared by every worktree of a repository) | `CLAUDE_CODE_DISABLE_AUTO_MEMORY=1` |
| background tasks and `/loop` wakeups | `CLAUDE_CODE_DISABLE_BACKGROUND_TASKS=1` |

Orchestration guard hooks (optional, `specyrd init --install-orchestration-hooks`) deny executors `git push`, `gh pr`, worktree and cloud commands; reviewers also deny `git commit`.

## Strengths
- Every Claude Fable 5.2 display name in Cursor's inventory says 1M [S1] (confidence: medium)
## Failure modes
- No failure modes observed; not piloted [S1]
## Code and test tendencies
- Opus 4.5 and 4.6 tend to over-engineer: extra files, unnecessary abstractions, flexibility that was not requested; Anthropic's own prompting guidance, live page read 2026-10-27 (researched 2026-10-27 from the lean-code reports, not human-verified) [S2]
- Opus 5 verifies its own work unprompted; self-check instructions cause over-verification (Anthropic prompting best practices, read 2026-10-27; researched 2026-10-27 from the lean-code reports, not human-verified) [S2]
- Claude Code PRs measured largest and deepest in the field: median 495 changed lines vs 52 human, nesting depth 4 vs 3, highest branch density; n=459, task mix confounded (Kraishan, 2026-09-12; researched 2026-10-27 from the lean-code reports, not human-verified) [S3]
- Strong test oracles: Claude Code is among the agents with the strongest assertion signals in field PRs (Banik et al., 2026-06; researched 2026-10-27 from the lean-code reports, not human-verified) [S4]
## Prompting rules
- Set effort explicitly; no host source names a default effort for this model [S1]
- Name the smallest behaviour-complete change and forbid extra files, abstractions, fallbacks and validation inside boundaries; the family's measured risk is diff size and depth, not weak tests [S2, S3]
## Open questions
- Price per token, output-token limit and release date are unknown here: no source on this host gives them; M22.72's dated report is to supply them
- Not piloted in any role; the role scores are the not-piloted default until a pilot or M22.72's report gives evidence
- The vendor's documented default effort and the levels Claude Code's --effort accepts for this model are not known here; Cursor's ids give levels low to max and mark no default [S1]; M22.72 to confirm
- Cursor no longer lists -thinking ids for Fable 5.2 (Fable 5.1 had them); whether thinking is always on is not known here [S1]
## Sources
- S1: Cursor agent model inventory (`agent models`), agent 2026.11.17-f532c45, harness-captures/cursor/inventory-models.txt, captured 2026-11-19, runtime
- S2: Claude prompting best practices (over-engineering and self-check notes), Anthropic, accessed 2026-10-27, https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/claude-prompting-best-practices, primary (lean-code reports)
- S3: Not All Agents Are Equal: Code Quality and Post-Merge Maintenance Across Five Autonomous Coding Agents in the Wild, Kraishan, arXiv 2609.17598, 2026-09-12, https://arxiv.org/html/2609.17598, independent (lean-code reports)
- S4: All Smoke, No Alarm: Oracle Signals in Agent-Authored Test Code, Banik, Chowdhury and Shamim, arXiv 2606.18168, 2026-06, https://arxiv.org/html/2606.18168v1, independent (lean-code reports)
