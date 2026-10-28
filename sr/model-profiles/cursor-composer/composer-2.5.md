---
profile_schema: 2
family: Cursor Composer
track: none
model: Composer 2.5
api_id: composer-2.5   # Cursor CLI slug, listed by `agent --list-models` on 2026.10.22 (2026-10-28)
checkpoint: unknown
alias_moves: unknown
version_rank: latest
release_date: 2026-05-18
researched: 2026-10-26
researcher: claude
supersedes: unknown
access:
  context_tokens: unknown
  output_tokens: unknown
  cli: agent -p --force "<prompt>"
  cli_verified_from: S2
  subagents: unknown Cursor supports parallel agents in worktrees; model-specific data not found [S3]
  effort_controls: none documented; Standard and Fast variants
  effort_map: { minimal: unknown, low: unknown, medium: unknown, high: unknown, max: unknown }
cost_usd_per_mtok: { input: 0.50, output: 2.50, cached_input: unknown, fast_input: 3.00, fast_output: 15.00 }
data_handling: 'Runs only inside Cursor (IDE, CLI, SDK); no public API [S4, S5]. Built on Moonshot''s Kimi K2.5 open-weight base, but Composer weights are not distributed [S5]. Cursor''s retention and privacy-mode terms were not researched: unknown. The file slug is a label, not a verified model id.'
role_fit:
  coordinator: { score: 2, reason: 'Harness-locked; no orchestration evidence', sources: [S1] }
  executor:    { score: 4, reason: '$0.50/$2.50 with vendor-reported gains on long-running tasks; third parties report SWE-Bench Multilingual parity with Opus 4.7 and GPT-5.5', sources: [S1, S4] }
  reviewer:    { score: 2, reason: 'Trained for doing, not judging; no review data', sources: [S1] }
---
## Strengths
- Lowest price in this roster: $0.50 input / $2.50 output; Fast variant $3/$15 with the same intelligence (vendor) [S1] (confidence: high)
- Vendor reports better sustained work on long tasks and more reliable instruction following than Composer 2, and says these are "not well captured by existing benchmarks" [S1] (confidence: low)
## Failure modes
- Headless runs silently propose instead of applying edits | trigger: agent -p without --force | mitigation in prompt: pass --force when edits are intended; omit it for review-only runs [S2]
## Code and test tendencies
- Cursor PRs: median 96 changed lines, the largest after Claude Code; revert rate indistinguishable from humans (Kraishan, 2026-09-12; researched 2026-10-27 from the lean-code reports, not human-verified) [S6]
- Mocks: agent commits that add tests add mocks more often, 36 percent vs 26 percent for non-agent commits (Hora and Robbes, 2026-01-30, pooled across agents), and Cursor PRs carried weaker test oracles than Claude Code and Devin (Banik et al., 2026-06; researched 2026-10-27 from the lean-code reports, not human-verified) [S7, S8]
## Prompting rules
- Use print mode with --output-format json or stream-json for machine-readable results [S3]
- Restrict the working directory and pass an explicit permission policy in CI [S2]
- Forbid new mocks where a real or fake boundary is practical and require each test to assert an output, error or state; mock-heavy, weak-oracle tests are the measured signature here [S7, S8]
## Change from previous version
- improved: trained on 25x more synthetic tasks on the same Kimi K2.5 base [S5]
- improved: instruction following and effort calibration (vendor) [S1]
## Open questions
- Benchmark parity claims with Opus 4.7 and GPT-5.5 come from secondary sources [S4];\[10\]\[11\] the frontier has moved since (Opus 5.5, GPT-6.1 Sol).
- No Composer release after 2.5 was found as of 2026-10-26.
## Sources
- S1: Introducing Composer 2.5, Cursor, 2026-05-18, https://cursor.com/blog/composer-2-5, primary (claude run)
- S2: Using Headless CLI, Cursor, accessed 2026-10-26, https://cursor.com/docs/cli/headless, primary (claude run)
- S3: Using Agent in CLI, Cursor, accessed 2026-10-26, https://cursor.com/docs/cli/using, primary (claude run)
- S4: Composer 2.5: Benchmarks, Pricing, and How It Compares, DataCamp, 2026-05, https://www.datacamp.com/blog/composer-2-5, independent (claude run)
- S5: Cursor Composer 2.5: Agent Coding at 1/10 the Cost, Digital Applied, 2026-05-18, https://www.digitalapplied.com/blog/cursor-composer-2-5-agent-coding-launch, independent (claude run)
- S6: Not All Agents Are Equal: Code Quality and Post-Merge Maintenance Across Five Autonomous Coding Agents in the Wild, Kraishan, arXiv 2609.17598, 2026-09-12, https://arxiv.org/html/2609.17598, independent (lean-code reports)
- S7: Agents overuse mocks: mock-adding commits 36 percent agent vs 26 percent non-agent across 1.2M commits in 2,168 repositories, Hora and Robbes, MSR 2026, 2026-01-30, no URL in the report, independent (lean-code reports)
- S8: All Smoke, No Alarm: Oracle Signals in Agent-Authored Test Code, Banik, Chowdhury and Shamim, arXiv 2606.18168, 2026-06, https://arxiv.org/html/2606.18168v1, independent (lean-code reports)
