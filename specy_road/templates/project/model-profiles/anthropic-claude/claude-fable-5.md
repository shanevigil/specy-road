---
profile_schema: 2
family: Anthropic Claude
track: Fable
model: Claude Fable 5
api_id: claude-fable-5
checkpoint: same-as-api_id
alias_moves: 'no'
version_rank: previous
release_date: 2026-06-09
researched: 2026-10-26
researcher: claude
supersedes: none
access:
  context_tokens: 1000000
  output_tokens: 128000
  cli: claude -p "<prompt>"
  cli_verified_from: S4
  subagents: unknown No model-specific data found
  effort_controls: 'effort parameter, default high; full level list not verified'
  effort_map: { minimal: unknown, low: unknown, medium: unknown, high: high, max: unknown }
cost_usd_per_mtok: { input: 10.00, output: 50.00, cached_input: 1.00, fast_input: unknown, fast_output: unknown }
data_handling: 'Same channels as Fable 5.1 once restored. Availability incident: on 2026-06-12 Anthropic suspended all access to Fable 5 and Mythos 5 to comply with a U.S. Department of Commerce export-control directive covering any foreign national; controls were lifted 2026-06-30 and Fable 5 access returned globally on 2026-07-01 on Claude Platform, Claude.ai, Claude Code and Cowork, with AWS, Google Cloud and Microsoft Foundry restored later [S2, S3, S5]. This is outside the 90-day window but shows that regulatory action can remove access to this track with no notice. Retention terms: unknown. No local deployment.'
role_fit:
  coordinator: { score: 3, reason: 'Superseded by Fable 5.1 at the same input/output price with cheaper cache reads', sources: [S1] }
  executor:    { score: 4, reason: 'AA Agentic Index 51.0 vs 58.0 for Fable 5.1', sources: [S6] }
  reviewer:    { score: 3, reason: 'Same model lineage as Fable 5.1 and Mythos; no independent review value against them', sources: [S1] }
---
## Strengths
- Led ARC-AGI-1 among listed models in August 2026 (aggregator reading) [S7] (confidence: low)
## Failure modes
- unknown: no failure mode met the inclusion bar (vendor documentation or two independent community reports)
## Code and test tendencies
- Opus 4.5 and 4.6 tend to over-engineer: extra files, unnecessary abstractions, flexibility that was not requested; Anthropic's own prompting guidance, live page read 2026-10-27 (researched 2026-10-27 from the lean-code reports, not human-verified) [S9]
- Opus 5 verifies its own work unprompted; self-check instructions cause over-verification (Anthropic prompting best practices, read 2026-10-27; researched 2026-10-27 from the lean-code reports, not human-verified) [S9]
- Claude Code PRs measured largest and deepest in the field: median 495 changed lines vs 52 human, nesting depth 4 vs 3, highest branch density; n=459, task mix confounded (Kraishan, 2026-09-12; researched 2026-10-27 from the lean-code reports, not human-verified) [S10]
- Strong test oracles: Claude Code is among the agents with the strongest assertion signals in field PRs (Banik et al., 2026-06; researched 2026-10-27 from the lean-code reports, not human-verified) [S11]
## Prompting rules
- Migrate to Fable 5.1; Anthropic marks Fable 5 legacy [S1]
- Build a fallback model path for this track; access was suspended for 19 days in June 2026 [S2, S3]
- Name the smallest behaviour-complete change and forbid extra files, abstractions, fallbacks and validation inside boundaries; this family's measured risk is diff size and depth, not weak tests [S9, S10]
## Change from previous version
- unknown: first Fable release; no earlier version in this track
## Open questions
- Biology safeguards were revised on 2026-08-06 to reduce false positives [S8]; impact on coding tasks unknown.
## Sources
- S1: Claude Fable 5 overview, Anthropic, accessed 2026-10-26, https://platform.claude.com/docs/en/models/fable-5/overview, primary (claude run)
- S2: Anthropic says Trump admin has lifted export controls on Claude Fable 5 and Mythos 5, CNBC, 2026-06-30, https://www.cnbc.com/2026/06/30/anthropic-says-trump-admin-has-lifted-export-controls-on-claude-fable-5-and-mythos-5.html, independent (claude run)
- S3: Anthropic restores AI models Fable, Mythos after the U.S. lifts export controls, CoinDesk, 2026-07-01, https://www.coindesk.com/tech/2026/07/01/anthropic-restores-ai-models-fable-mythos-after-the-u-s-lifts-export-controls, independent (claude run)
- S4: Run Claude Code programmatically, Anthropic, accessed 2026-10-26, https://code.claude.com/docs/en/headless, primary (claude run)
- S5: Anthropic statement on Fable and Mythos access, Anthropic, 2026-06-30, https://www.anthropic.com/news/fable-mythos-access, primary (user-supplied; not retrieved in this research) (claude run)
- S6: AA Agentic Index Leaderboard, BenchLM, 2026-10-10, https://benchlm.ai/benchmarks/aaagenticindex, independent (claude run)
- S7: Top AI Models Ranked on LLM Leaderboards, Green Flag Digital, 2026-08-21, https://greenflagdigital.com/top-ai-models-ranked/, independent (claude run)
- S8: Claude Fable, Anthropic, accessed 2026-10-26, https://www.anthropic.com/claude/fable, primary (claude run)
- S9: Claude prompting best practices (over-engineering and self-check notes), Anthropic, accessed 2026-10-27, https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/claude-prompting-best-practices, primary (lean-code reports)
- S10: Not All Agents Are Equal: Code Quality and Post-Merge Maintenance Across Five Autonomous Coding Agents in the Wild, Kraishan, arXiv 2609.17598, 2026-09-12, https://arxiv.org/html/2609.17598, independent (lean-code reports)
- S11: All Smoke, No Alarm: Oracle Signals in Agent-Authored Test Code, Banik, Chowdhury and Shamim, arXiv 2606.18168, 2026-06, https://arxiv.org/html/2606.18168v1, independent (lean-code reports)
