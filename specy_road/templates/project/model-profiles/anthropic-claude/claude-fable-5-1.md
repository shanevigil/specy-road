---
profile_schema: 2
family: Anthropic Claude
track: Fable
model: Claude Fable 5.1
api_id: claude-fable-5-1
checkpoint: same-as-api_id
alias_moves: 'no'
version_rank: latest
release_date: 2026-09-01
researched: 2026-10-26
researcher: claude
supersedes: claude-fable-5
access:
  context_tokens: 1000000
  output_tokens: 128000
  cli: claude -p "<prompt>"
  cli_verified_from: S4
  subagents: 'unknown Vendor and partner pages describe multi-hour autonomous work; a third party reports fewer parallel tool calls than Fable 5 [S2, S3]'
  effort_controls: 'effort parameter, default high; mid-conversation effort change in beta; full level list not verified'
  effort_map: { minimal: unknown, low: unknown, medium: unknown, high: high, max: unknown }
cost_usd_per_mtok: { input: 10.00, output: 50.00, cached_input: 0.25, fast_input: unknown, fast_output: unknown }
data_handling: 'Anthropic designates Fable 5.1 a "Covered Model" with additional data retention, safety review and access policies wherever offered [S2]. Available on the Claude API, Amazon Bedrock (US geo and global inference profiles), Claude Platform on AWS (North America), Google Cloud and Microsoft Foundry [S1, S5]. Outputs carry content provenance (watermarking) [S1, S3]. Claude Mythos 5.1, the same model with fewer cyber and bio restrictions, is limited to verified organizations [S1]. Exact retention period: unknown. No local deployment.'
role_fit:
  coordinator: { score: 4, reason: 'Strongest Anthropic GA model on long-horizon work but "Slower" latency and 2.5x Opus 5.5 price; Anthropic itself says start with Opus 5.5', sources: [S1] }
  executor:    { score: 5, reason: 'Terminal-Bench 4.0 55.8 percent vs 42.0 for Fable 5 (vendor), first on AA Agentic Index (58.0)', sources: [S3, S6] }
  reviewer:    { score: 4, reason: 'Partner page reports it says when stuck instead of claiming success and is less likely to disable failing tests', sources: [S2] }
---
## Strengths
- Terminal-Bench 4.0: 55.8 percent vs 42.0 percent for Fable 5 and 52.3 percent for Opus 5 (vendor-reported); Anthropic reported Claude Mythos 5.1 (the same model with looser safeguards) at 60.9 percent and says the gap "reflects the tasks on which our earlier, less precise cyber safeguards intervened" [S3, S7] (confidence: medium)
- First on the Artificial Analysis Agentic Index at 58.0 in an October 2026 aggregator [S6] (confidence: medium)
- Reports being stuck instead of reporting success, and is less likely to disable a failing test (vendor claim via AWS) [S2] (confidence: low)\[1\]
## Failure modes
- Issues fewer parallel tool calls than Fable 5, sometimes one tool per turn | trigger: long-running agent loops | mitigation in prompt: state explicitly which independent reads or checks may run in parallel [S3]
- Quality not monotonic in effort: one third-party composite peaked at medium effort, below Fable 5's best | trigger: high effort settings | mitigation in prompt: benchmark medium and high on your own tasks before defaulting to high [S3]
## Code and test tendencies
- Opus 4.5 and 4.6 tend to over-engineer: extra files, unnecessary abstractions, flexibility that was not requested; Anthropic's own prompting guidance, live page read 2026-10-27 (researched 2026-10-27 from the lean-code reports, not human-verified) [S8]
- Opus 5 verifies its own work unprompted; self-check instructions cause over-verification (Anthropic prompting best practices, read 2026-10-27; researched 2026-10-27 from the lean-code reports, not human-verified) [S8]
- Claude Code PRs measured largest and deepest in the field: median 495 changed lines vs 52 human, nesting depth 4 vs 3, highest branch density; n=459, task mix confounded (Kraishan, 2026-09-12; researched 2026-10-27 from the lean-code reports, not human-verified) [S9]
- Strong test oracles: Claude Code is among the agents with the strongest assertion signals in field PRs (Banik et al., 2026-06; researched 2026-10-27 from the lean-code reports, not human-verified) [S10]
## Prompting rules
- Use Opus 5.5 first; escalate to Fable 5.1 only when Opus 5.5 at higher effort fails your evals [S1]
- Do not use forced tool use; it returns an error [S1]
- Do not edit earlier turns; edits invalidate thinking blocks [S1]
- Use turn-scoped system messages (beta) for per-turn instructions instead of rewriting the system prompt [S1]
- Follow the model-specific guide "Prompting Claude Fable 5.1" for long-horizon work (not read in this research) [S1]
- Name the smallest behaviour-complete change and forbid extra files, abstractions, fallbacks and validation inside boundaries; this family's measured risk is diff size and depth, not weak tests [S8, S9]
## Change from previous version
- improved: cache read $1.00 to $0.25 per MTok; input/output unchanged [S1, S5]
- improved: Terminal-Bench 4.0 42.0 to 55.8 percent [S3]
- improved: about 60 percent fewer cyber-safeguard interventions per Claude Code session [S3, S5]
- regressed: forced tool use errors; thinking blocks readable only by Fable 5.1 and Mythos 5.1 [S1]
- regressed: fewer parallel tool calls per turn [S3]
## Open questions
- Effort level names for Fable 5.1 were not confirmed on a vendor page; Caylent mentions "auto and none" as supported values for a changed parameter without naming it clearly [S3].
## Sources
- S1: Claude Fable 5.1 overview, Anthropic, 2026-09-01, https://platform.claude.com/docs/en/models/fable-5-1/overview, primary (claude run)
- S2: Claude Fable 5.1 is now available on AWS, Amazon Web Services, 2026-09, https://aws.amazon.com/about-aws/whats-new/2026/09/claude-fable-5-1-aws/, primary (claude run)
- S3: Claude Fable 5.1: What Changed From Fable 5 and What to Validate, Caylent, 2026-09, https://caylent.com/blog/claude-fable-5-1-what-changed-from-fable-5-and-what-to-validate, independent (claude run)
- S4: Run Claude Code programmatically, Anthropic, accessed 2026-10-26, https://code.claude.com/docs/en/headless, primary (claude run)
- S5: Anthropic's Claude Fable 5.1 and Mythos 5.1 arrive with a 75% cost reduction for Fable cache reads, VentureBeat, 2026-09-01, https://venturebeat.com/technology/anthropics-claude-fable-5-1-and-mythos-5-1-arrive-with-a-75-cost-reduction-for-fable-cache-reads, independent (claude run)
- S6: AA Agentic Index Leaderboard, BenchLM, 2026-10-10, https://benchlm.ai/benchmarks/aaagenticindex, independent (claude run)
- S7: Introducing Claude Fable 5.1 and Claude Mythos 5.1, Anthropic, 2026-09-01, https://www.anthropic.com/claude-fable-and-mythos-5-1, primary (claude run)
- S8: Claude prompting best practices (over-engineering and self-check notes), Anthropic, accessed 2026-10-27, https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/claude-prompting-best-practices, primary (lean-code reports)
- S9: Not All Agents Are Equal: Code Quality and Post-Merge Maintenance Across Five Autonomous Coding Agents in the Wild, Kraishan, arXiv 2609.17598, 2026-09-12, https://arxiv.org/html/2609.17598, independent (lean-code reports)
- S10: All Smoke, No Alarm: Oracle Signals in Agent-Authored Test Code, Banik, Chowdhury and Shamim, arXiv 2606.18168, 2026-06, https://arxiv.org/html/2606.18168v1, independent (lean-code reports)
