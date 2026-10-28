---
profile_schema: 2
family: Cursor Composer
track: none
model: Composer 2
api_id: unknown
checkpoint: unknown
alias_moves: unknown
version_rank: previous
release_date: 2026-03-19
researched: 2026-10-26
researcher: claude
supersedes: none
access:
  context_tokens: unknown
  output_tokens: unknown
  cli: agent -p --force "<prompt>"
  cli_verified_from: S2
  subagents: unknown No data found
  effort_controls: none documented; Fast is the default variant
  effort_map: { minimal: unknown, low: unknown, medium: unknown, high: unknown, max: unknown }
cost_usd_per_mtok: { input: unknown, output: unknown, cached_input: unknown, fast_input: unknown, fast_output: unknown }
data_handling: 'Cursor-only, as for Composer 2.5 [S1]. Details unknown. Possibly stale: released more than 180 days before the research date.'
role_fit:
  coordinator: { score: 1, reason: 'Superseded and harness-locked', sources: [S1] }
  executor:    { score: 3, reason: 'Still selectable in Cursor; superseded by 2.5 on the same base', sources: [S1, S3] }
  reviewer:    { score: 1, reason: 'No review data', sources: [S1] }
---
## Strengths
- Built on Kimi K2.5 with Cursor RL post-training; documented in a Composer 2 technical report (not read) [S3] (confidence: low)
## Failure modes
- unknown: no failure mode met the inclusion bar
## Code and test tendencies
- Cursor PRs: median 96 changed lines, the largest after Claude Code; revert rate indistinguishable from humans (Kraishan, 2026-09-12; researched 2026-10-27 from the lean-code reports, not human-verified) [S4]
- Mocks: agent commits that add tests add mocks more often, 36 percent vs 26 percent for non-agent commits (Hora and Robbes, 2026-01-30, pooled across agents), and Cursor PRs carried weaker test oracles than Claude Code and Devin (Banik et al., 2026-06; researched 2026-10-27 from the lean-code reports, not human-verified) [S5, S6]
## Prompting rules
- Prefer Composer 2.5, which is the default in the model picker [S1]
- Forbid new mocks where a real or fake boundary is practical and require each test to assert an output, error or state; mock-heavy, weak-oracle tests are the measured signature here [S5, S6]
## Change from previous version
- unknown: Composer 1.5 comparison not researched
## Open questions
- Pricing not found in sources read; possibly stale (older than 180 days).
## Sources
- S1: Composer 2.5: Benchmarks, Pricing, and How It Compares, DataCamp, 2026-05, https://www.datacamp.com/blog/composer-2-5, independent (claude run)
- S2: Using Headless CLI, Cursor, accessed 2026-10-26, https://cursor.com/docs/cli/headless, primary (claude run)
- S3: Cursor Composer 2.5 Developer Guide, Lushbinary, 2026-05, https://lushbinary.com/blog/cursor-composer-2-5-developer-guide-benchmarks-pricing/, independent (claude run)
- S4: Not All Agents Are Equal: Code Quality and Post-Merge Maintenance Across Five Autonomous Coding Agents in the Wild, Kraishan, arXiv 2609.17598, 2026-09-12, https://arxiv.org/html/2609.17598, independent (lean-code reports)
- S5: Agents overuse mocks: mock-adding commits 36 percent agent vs 26 percent non-agent across 1.2M commits in 2,168 repositories, Hora and Robbes, MSR 2026, 2026-01-30, no URL in the report, independent (lean-code reports)
- S6: All Smoke, No Alarm: Oracle Signals in Agent-Authored Test Code, Banik, Chowdhury and Shamim, arXiv 2606.18168, 2026-06, https://arxiv.org/html/2606.18168v1, independent (lean-code reports)
